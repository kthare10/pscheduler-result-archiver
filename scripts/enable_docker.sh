#!/bin/bash
set -euo pipefail

# --- Detect IP type (management connectivity heuristic) ---
if command -v ping6 >/dev/null 2>&1; then
    ping6 -c 1 -W 1 google.com &>/dev/null && man_ip_type=ipv6 || man_ip_type=ipv4
else
    ping -6 -c 1 -W 1 google.com &>/dev/null && man_ip_type=ipv6 || man_ip_type=ipv4
fi

# --- Detect OS and version ---
source /etc/os-release
os_id=$ID
os_version_id=$(echo "${VERSION_ID:-}" | cut -d'.' -f1)

# Determine the real login user (works when run via sudo)
TARGET_USER="${SUDO_USER:-$USER}"

echo "Detected OS: $os_id, Version: $os_version_id (man_ip_type=${man_ip_type}, target_user=${TARGET_USER})"

install_ubuntu_common() {
    sudo apt-get update -y
    sudo apt-get install -y apt-transport-https ca-certificates curl software-properties-common gnupg lsb-release jq
    curl -fsSL https://get.docker.com | sudo sh
    sudo mkdir -p /etc/docker

    # add target user to docker group (create group if missing)
    sudo groupadd -f docker
    sudo usermod -aG docker "$TARGET_USER"

    sudo apt-get install -y openvswitch-switch
    sudo systemctl enable --now openvswitch-switch
    sudo apt-get install -y build-essential wget tcpdump iftop python3-pip
    sudo apt install -y python3-dev build-essential libatlas-base-dev
}

install_python_libs() {
    python3 -m pip install docker rpyc --user --break-system-packages || python3 -m pip install docker rpyc --user
}

ensure_pip39() {
    if ! command -v pip3.9 &>/dev/null; then
        echo "pip3.9 not found, installing..."
        curl -sS https://bootstrap.pypa.io/get-pip.py | sudo python3.9
        if ! echo "$PATH" | grep -q "/usr/local/bin"; then
            echo 'export PATH="/usr/local/bin:$PATH"' >> ~/.bashrc
            export PATH="/usr/local/bin:$PATH"
            echo "Added /usr/local/bin to PATH. You may 'source ~/.bashrc' if not re-execing below."
        fi
    fi
}

install_rocky_common() {
    sudo dnf install -y epel-release
    sudo dnf config-manager --add-repo=https://download.docker.com/linux/centos/docker-ce.repo
    sudo dnf install -y docker-ce docker-ce-cli containerd.io jq
    sudo mkdir -p /etc/docker
    sudo systemctl enable --now docker

    # add target user to docker group (create group if missing)
    sudo groupadd -f docker
    sudo usermod -aG docker "$TARGET_USER"

    sudo dnf install -y firewalld git
    sudo dnf install -y python3-devel gcc gcc-c++ redhat-rpm-config
    sudo dnf install -y expect
    sudo systemctl enable --now firewalld
    sudo firewall-cmd --zone=public --add-port=5201/tcp --permanent
    sudo firewall-cmd --zone=public --add-port=5201/udp --permanent
    sudo firewall-cmd --reload
}

# --- Configure Docker for IPv6 if management IP is IPv6 ---
configure_docker_ipv6() {
    if [[ "$man_ip_type" != "ipv6" ]]; then
        echo "Management IP is IPv4; skipping Docker IPv6 config."
        return 0
    fi

    echo "Configuring Docker IPv6 in /etc/docker/daemon.json ..."

    sudo mkdir -p /etc/docker
    # Backup existing daemon.json if present
    if [[ -f /etc/docker/daemon.json ]]; then
        sudo cp -a /etc/docker/daemon.json /etc/docker/daemon.json.bak.$(date +%s)
    else
        echo '{}' | sudo tee /etc/docker/daemon.json >/dev/null
    fi

    # Default DNS servers (Cloudflare + Google IPv6)
    DEFAULT_DNS='["2606:4700:4700::1111", "2001:4860:4860::8888"]'

    # Merge/update daemon.json with jq
    tmpfile=$(mktemp)
    sudo jq --argjson dns "$DEFAULT_DNS" '
        .ipv6 = true
        | .dns = ($dns)
    ' /etc/docker/daemon.json | sudo tee "$tmpfile" >/dev/null

    sudo mv "$tmpfile" /etc/docker/daemon.json

    # Restart Docker to apply
    if command -v systemctl >/dev/null 2>&1; then
        sudo systemctl daemon-reload || true
        sudo systemctl restart docker
        sudo systemctl enable docker || true
    else
        sudo service docker restart || true
    fi

    echo "Docker IPv6 configured."
}

# ---------------- MTU-SAFE HELPERS (avoid 'mtu greater than device maximum') ----------------

is_skippable_iface() {
  local d="$1"
  [[ "$d" == "lo" ]] && return 0
  [[ "$d" == docker* || "$d" == veth* || "$d" == br-* || "$d" == cni* || "$d" == flannel* ]] && return 0
  [[ "$d" == cilium* || "$d" == wg* || "$d" == tun* || "$d" == tap* || "$d" == virbr* || "$d" == vmnet* ]] && return 0
  [[ "$d" == nm-* || "$d" == ovs-system || "$d" == ovs-* || "$d" == ppp* || "$d" == team* || "$d" == bond* ]] && return 0
  return 1
}

get_max_mtu() {
  local d="$1" max=""
  if [[ -r "/sys/class/net/$d/dev_max_mtu" ]]; then
    max=$(cat "/sys/class/net/$d/dev_max_mtu" 2>/dev/null || echo "")
  fi
  if [[ -z "$max" ]]; then
    max=$(ip -d link show "$d" 2>/dev/null | awk '/maxmtu/ {for(i=1;i<=NF;i++){if($i~"maxmtu"){print $(i+1); exit}}}')
  fi
  [[ "$max" =~ ^[0-9]+$ ]] && echo "$max" || echo ""
}

get_min_mtu() {
  local d="$1" min=""
  if [[ -r "/sys/class/net/$d/dev_min_mtu" ]]; then
    min=$(cat "/sys/class/net/$d/dev_min_mtu" 2>/dev/null || echo "")
  fi
  if [[ -z "$min" ]]; then
    min=$(ip -d link show "$d" 2>/dev/null | awk '/minmtu/ {for(i=1;i<=NF;i++){if($i~"minmtu"){print $(i+1); exit}}}')
  fi
  [[ "$min" =~ ^[0-9]+$ ]] && echo "$min" || echo ""
}

apply_mtu_if_supported() {
  local d="$1" target="${2:-9000}"
  local max min cur
  max=$(get_max_mtu "$d")
  min=$(get_min_mtu "$d")
  cur=$(cat "/sys/class/net/$d/mtu" 2>/dev/null || echo "")

  # If we can’t determine limits, don’t touch it
  if [[ -z "$max" || -z "$min" || -z "$cur" ]]; then
    echo "[mtu] $d: unknown limits; skipping"
    return 0
  fi

  # Clamp target to device range
  if (( target > max )); then
    echo "[mtu] $d: requested $target > max $max; clamping to $max"
    target="$max"
  fi
  if (( target < min )); then
    echo "[mtu] $d: requested $target < min $min; clamping to $min"
    target="$min"
  fi

  # Only change if different
  if (( target != cur )); then
    if sudo ip link set dev "$d" mtu "$target" 2>/dev/null; then
      echo "[mtu] $d: set MTU $cur -> $target"
    else
      echo "[mtu] $d: failed to set MTU to $target; leaving at $cur"
    fi
  else
    echo "[mtu] $d: already $cur; ok"
  fi
}

# ---------------- End MTU-SAFE HELPERS ----------------

host_tune() {
    echo "Applying host tuning settings..."
    sudo tee -a /etc/sysctl.conf >/dev/null <<'EOL'
# allow testing with buffers up to 128MB
net.core.rmem_max = 536870912
net.core.wmem_max = 536870912
# increase Linux autotuning TCP buffer limit to 64MB
net.ipv4.tcp_rmem = 4096 87380 536870912
net.ipv4.tcp_wmem = 4096 65536 536870912
# recommended default congestion control is bbr
net.ipv4.tcp_congestion_control = bbr
# enable MTU probing so TCP adapts if path MTU is smaller
net.ipv4.tcp_mtu_probing = 1
# enable fair queueing
net.core.default_qdisc = fq
EOL
    sudo sysctl --system || true

    # Safely apply MTU up to 9000 only where supported
    for devpath in /sys/class/net/*; do
        dev=$(basename "$devpath")
        is_skippable_iface "$dev" && { echo "[mtu] $dev: skipping (virtual/loopback)"; continue; }
        state=$(cat "/sys/class/net/$dev/operstate" 2>/dev/null || echo "unknown")
        [[ "$state" == "down" ]] && { echo "[mtu] $dev: down; skipping"; continue; }
        apply_mtu_if_supported "$dev" 9000
    done
}

# --- Re-exec into a shell with new docker group (no logout required) ---
activate_docker_group_now() {
    echo "[*] Activating docker group for ${TARGET_USER} without logout…"
    sudo usermod -aG docker $(whoami)
    newgrp docker
}

# --- Main execution logic ---
case "$os_id" in
    ubuntu)
        case "$os_version_id" in
            20)
                install_ubuntu_common
                sudo apt-get install -y \
                    zlib1g-dev libncurses5-dev libgdbm-dev libnss3-dev libssl-dev libreadline-dev libffi-dev \
                    python3.9 python3.9-full
                python3.9 -m pip install docker rpyc --user
                configure_docker_ipv6
                ;;
            22|24)
                install_ubuntu_common
                sudo apt-get install -y \
                    checkinstall libncursesw5-dev libssl-dev libsqlite3-dev tk-dev libgdbm-dev libc6-dev libbz2-dev
                install_python_libs
                configure_docker_ipv6
                ;;
            *)
                echo "Unsupported Ubuntu version: $os_version_id"
                exit 1
                ;;
        esac
        ;;
    rocky)
        case "$os_version_id" in
            8)
                install_rocky_common
                sudo dnf install -y https://repos.fedorapeople.org/repos/openstack/openstack-yoga/rdo-release-yoga-1.el8.noarch.rpm
                sudo dnf install -y openvswitch libibverbs tcpdump net-tools python3.9 vim iftop
                ensure_pip39
                pip3.9 install docker rpyc --user
                sudo systemctl enable --now openvswitch
                sudo sysctl --system || true
                configure_docker_ipv6
                ;;
            9)
                install_rocky_common
                sudo dnf install -y centos-release-nfv-openvswitch
                sudo dnf install -y openvswitch3.3 libibverbs tcpdump net-tools python vim iftop
                ensure_pip39
                pip3.9 install docker rpyc --user
                sudo systemctl enable --now openvswitch
                sudo sysctl --system || true
                configure_docker_ipv6
                ;;
            *)
                echo "Unsupported Rocky version: $os_version_id"
                exit 1
                ;;
        esac
        ;;
    *)
        echo "Unsupported OS: $os_id"
        exit 1
        ;;
esac

host_tune

# <<< key addition to activate docker group now >>>
#activate_docker_group_now

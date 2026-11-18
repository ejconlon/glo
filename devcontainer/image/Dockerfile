FROM docker.io/rockylinux/rockylinux:10.3.20261112.0-minimal@sha256:f819149e93579b96a7e2fb7286dae4756173de68aafcc78e7e659650c6867b7b

USER root
WORKDIR /root

RUN --mount=type=cache,target=/var/cache/dnf,id=dnf-cache-dev,sharing=locked \
    --mount=type=cache,target=/var/lib/dnf,id=dnf-lib-dev,sharing=locked \
    microdnf -y install epel-release \
    && microdnf -y --setopt=install_weak_deps=0 install \
        bind-utils \
        bzip2 \
        ca-certificates \
        chafa \
        curl \
        file \
        findutils \
        gcc \
        gcc-c++ \
        gh \
        git \
        gnupg2 \
        gzip \
        htop \
        iputils \
        iproute \
        lsof \
        make \
        nano \
        ncurses \
        neovim \
        openssh-clients \
        pandoc \
        patch \
        perf \
        dnf-plugins-core \
        net-tools \
        nmap \
        nmap-ncat \
        unzip \
        inotify-tools \
        jq \
        less \
        libatomic \
        pv \
        pkgconf-pkg-config \
        procps-ng \
        psmisc \
        python3.12 \
        python3.12-pip \
        readline \
        rsync \
        ripgrep \
        ShellCheck \
        sqlite \
        sqlite-devel \
        strace \
        tar \
        tmux \
        tree \
        time \
        vim-enhanced \
        vim-minimal \
        wget \
        whois \
        which \
        xz \
        yq \
        zip \
        zstd \
        gmp-devel \
        libffi-devel \
        zlib-devel \
    && groupadd --gid 1000 user \
    && useradd --uid 1000 --gid 1000 --create-home --shell /bin/bash user

# Build Caddy with the pinned Layer 4 module using a temporary Go toolchain.
# The default image contains no Caddy executable.
ARG CADDY_ENABLED=0
# Caddy v2.11.9.
ARG CADDY_COMMIT=0d98caea58f794f88e709b1bef2880996a471bca
ARG CADDY_SOURCE_SHA256=7b8de20699ec38a43c97d70dd5347ed8e19d3db96d0c9d76ded020f018cb6e5e
# caddy-l4 v0.1.3.
ARG CADDY_L4_COMMIT=eafc300ef23bcb2a28cc329a18e1e98bcd2b7cee
ARG CADDY_L4_SOURCE_SHA256=18b9c1280e292a8970586c270ac96e52cd2c6f6f419e23fdb50125c9035679d1
# xcaddy v0.4.7.
ARG XCADDY_COMMIT=e0e8f68a0f4bef11bfd04c4fb3091052ad36132f
ARG XCADDY_SOURCE_SHA256=3f739ceb6cf2cf2eb2dd8e8004e31543ad6862b2824b2fd68be2c517c90b1c49
ARG CADDY_GO_VERSION=1.27.4
ARG CADDY_GO_SHA256_X64=7226736c2339719cda28fbf3a54d71aa63bcefe376e98cef00034268dab24840
ARG CADDY_GO_SHA256_ARM64=3392582988a273a87ab5043ee1b2c9c17a2c3c00580bf9326c47a2e0aaaeac92
RUN if [ "${CADDY_ENABLED}" = "1" ]; then \
    set -eux; \
    arch="$(uname -m)"; \
    case "${arch}" in \
        x86_64) go_arch="amd64"; checksum="${CADDY_GO_SHA256_X64}" ;; \
        aarch64) go_arch="arm64"; checksum="${CADDY_GO_SHA256_ARM64}" ;; \
        *) echo "Unsupported architecture: ${arch}" >&2; exit 1 ;; \
    esac; \
    archive="go${CADDY_GO_VERSION}.linux-${go_arch}.tar.gz"; \
    url="https://go.dev/dl/${archive}"; \
    curl -fsSLo "/tmp/${archive}" "${url}"; \
    echo "${checksum}  /tmp/${archive}" | sha256sum -c -; \
    mkdir -p /tmp/caddy-build/toolchain /tmp/caddy-build/bin; \
    tar -xzf "/tmp/${archive}" -C /tmp/caddy-build/toolchain; \
    export PATH="/tmp/caddy-build/toolchain/go/bin:${PATH}"; \
    export GOBIN=/tmp/caddy-build/bin; \
    export GOPATH=/tmp/caddy-build/gopath; \
    export GOCACHE=/tmp/caddy-build/cache; \
    export GOMODCACHE=/tmp/caddy-build/modules; \
    export GOTOOLCHAIN=local; \
    export CGO_ENABLED=0; \
    fetch_source() { \
        source_name="$1"; \
        source_repository="$2"; \
        source_commit="$3"; \
        source_checksum="$4"; \
        source_archive="/tmp/caddy-build/${source_name}.tar.gz"; \
        source_directory="/tmp/caddy-build/source/${source_name}"; \
        curl -fsSLo "${source_archive}" \
            "https://codeload.github.com/${source_repository}/tar.gz/${source_commit}"; \
        echo "${source_checksum}  ${source_archive}" | sha256sum -c -; \
        mkdir -p "${source_directory}"; \
        tar -xzf "${source_archive}" --strip-components=1 -C "${source_directory}"; \
    }; \
    fetch_source caddy caddyserver/caddy \
        "${CADDY_COMMIT}" "${CADDY_SOURCE_SHA256}"; \
    fetch_source caddy-l4 mholt/caddy-l4 \
        "${CADDY_L4_COMMIT}" "${CADDY_L4_SOURCE_SHA256}"; \
    fetch_source xcaddy caddyserver/xcaddy \
        "${XCADDY_COMMIT}" "${XCADDY_SOURCE_SHA256}"; \
    cd /tmp/caddy-build/source/xcaddy; \
    go install ./cmd/xcaddy; \
    cd /root; \
    /tmp/caddy-build/bin/xcaddy build "${CADDY_COMMIT}" \
        --replace "github.com/caddyserver/caddy/v2=/tmp/caddy-build/source/caddy" \
        --with "github.com/mholt/caddy-l4@${CADDY_L4_COMMIT}" \
        --replace "github.com/mholt/caddy-l4=/tmp/caddy-build/source/caddy-l4" \
        --output /tmp/caddy-build/caddy; \
    install -m 0755 /tmp/caddy-build/caddy /usr/local/bin/caddy; \
    rm -rf /tmp/caddy-build "/tmp/${archive}"; \
    caddy version; \
    caddy list-modules | grep -Fx layer4; \
    caddy list-modules | grep -Fx layer4.handlers.proxy; \
    caddy list-modules | grep -Fx layer4.handlers.tls; \
    fi

# Install Garage from the official checksummed release binaries.
# The default image contains no Garage executable.
ARG GARAGE_ENABLED=0
ARG GARAGE_VERSION=2.5.0
ARG GARAGE_SHA256_X64=2ff667286217cd73ebcb1c03af993822365000441dfe31a80cb64c5189a9dea8
ARG GARAGE_SHA256_ARM64=69b6040cef428b993500c17dd0d0c1240acf2f3f667b9b05ceba4b9660db4e8c
RUN if [ "${GARAGE_ENABLED}" = "1" ]; then \
    set -eux; \
    arch="$(uname -m)"; \
    case "${arch}" in \
        x86_64) target="x86_64-unknown-linux-musl"; checksum="${GARAGE_SHA256_X64}" ;; \
        aarch64) target="aarch64-unknown-linux-musl"; checksum="${GARAGE_SHA256_ARM64}" ;; \
        *) echo "Unsupported architecture: ${arch}" >&2; exit 1 ;; \
    esac; \
    url="https://garagehq.deuxfleurs.fr/_releases/v${GARAGE_VERSION}/${target}/garage"; \
    curl -fsSLo /tmp/garage "${url}"; \
    echo "${checksum}  /tmp/garage" | sha256sum -c -; \
    install -m 0755 /tmp/garage /usr/local/bin/garage; \
    rm -f /tmp/garage; \
    garage --version; \
    fi

# Install an explicit PostgreSQL 18 client, server, and development boundary.
# The default image contains no PostgreSQL packages or initialized cluster.
ARG POSTGRES_ENABLED=0
ARG PGDG_REPO_RPM_VERSION=42.0-70
ARG PGDG_REPO_SHA256_X64=7cf263def272972281df755a31487b0eadabc91c424962705820435a90621a06
ARG PGDG_REPO_SHA256_ARM64=f52f305b4e2ead1db2614bd923e7d987c9821d0331c4bf3561a23ca4c634613b
# The common repository retains versioned RPMs; reporpms only keeps the latest.
RUN --mount=type=cache,target=/var/cache/dnf,id=dnf-cache-dev,sharing=locked \
    --mount=type=cache,target=/var/lib/dnf,id=dnf-lib-dev,sharing=locked \
    if [ "${POSTGRES_ENABLED}" = "1" ]; then \
    set -eux; \
    arch="$(uname -m)"; \
    case "${arch}" in \
        x86_64) repo_arch="x86_64"; checksum="${PGDG_REPO_SHA256_X64}" ;; \
        aarch64) repo_arch="aarch64"; checksum="${PGDG_REPO_SHA256_ARM64}" ;; \
        *) echo "Unsupported architecture: ${arch}" >&2; exit 1 ;; \
    esac; \
    repo_rpm="pgdg-redhat-repo-${PGDG_REPO_RPM_VERSION}.rhel10PGDG.noarch.rpm"; \
    curl -fsSLo "/tmp/${repo_rpm}" \
        "https://download.postgresql.org/pub/repos/yum/common/redhat/rhel-10-${repo_arch}/${repo_rpm}"; \
    echo "${checksum}  /tmp/${repo_rpm}" | sha256sum -c -; \
    rpm --install "/tmp/${repo_rpm}"; \
    microdnf -y --setopt=install_weak_deps=0 install \
        libpq5-devel \
        postgresql18 \
        postgresql18-server; \
    rm -f "/tmp/${repo_rpm}"; \
    /usr/pgsql-18/bin/psql --version | grep -E '^psql \(PostgreSQL\) 18\.'; \
    fi

ENV PATH="/usr/pgsql-18/bin:${PATH}"

# Use Python 3.14 for development; Rocky's /usr/bin/python3 remains available to RPM tools.
ARG PYTHON_VERSION=3.14.10
ARG PYTHON_BUILD_VERSION=20261110
ARG PYTHON_SHA256_X86_64=c2ff2e97422f5d3896a16e0317fd212ba977bbf2688d93a6f7a03d817506bd30
ARG PYTHON_SHA256_AARCH64=38fd50f07170adc29d481913d1c30b17ecb538fbe290315fe1f83d84fdd5b694
RUN set -eux; \
    arch="$(uname -m)"; \
    case "${arch}" in \
        x86_64) checksum="${PYTHON_SHA256_X86_64}" ;; \
        aarch64) checksum="${PYTHON_SHA256_AARCH64}" ;; \
        *) echo "Unsupported architecture: ${arch}" >&2; exit 1 ;; \
    esac; \
    curl -fsSLo /tmp/python.tar.gz \
        "https://github.com/astral-sh/python-build-standalone/releases/download/${PYTHON_BUILD_VERSION}/cpython-${PYTHON_VERSION}%2B${PYTHON_BUILD_VERSION}-${arch}-unknown-linux-gnu-install_only_stripped.tar.gz"; \
    echo "${checksum}  /tmp/python.tar.gz" | sha256sum -c -; \
    tar -xzf /tmp/python.tar.gz -C /opt; \
    rm /tmp/python.tar.gz

ENV PATH="/opt/python/bin:${PATH}"

# Install the selected Python tools from checksummed wheels into Python 3.14.
ARG PIP_VERSION=26.3
ARG PIP_SHA256=f3b60b20ffaadd4415ed7957212a38ac63fa4c5fa375bd0f4a797777940fad13
ARG UV_VERSION=0.13.9
ARG UV_SHA256_X64=d7f459fe4fd247d830351c75686d3996ace3c6f3f728eb0e85a30b7ada0cef19
ARG UV_SHA256_ARM64=ecb6028d79dc96fbeafffe5c8af62a7099487ebc05a701e76714eebcffd06375
RUN printf 'pip==%s --hash=sha256:%s\nuv==%s --hash=sha256:%s --hash=sha256:%s\n' \
        "${PIP_VERSION}" "${PIP_SHA256}" "${UV_VERSION}" "${UV_SHA256_X64}" "${UV_SHA256_ARM64}" \
        > /tmp/python-tools.txt \
    && python3 -m pip install --no-cache-dir --upgrade --only-binary=:all: \
        --require-hashes -r /tmp/python-tools.txt \
    && rm /tmp/python-tools.txt

# Install just from GitHub releases.
ARG JUST_ENABLED=1
ARG JUST_VERSION=1.59.0
ARG JUST_SHA256_X86_64=409044617b6f06517c1035e55ca38c8c856ff8b650e41bc2aa1ef82d5903a23e
ARG JUST_SHA256_AARCH64=23871b1702bfd550fb5f901778fd4290ecf2ee034a45a889fbe96d89b188086d
RUN if [ "${JUST_ENABLED}" = "1" ]; then \
    set -eux; \
    arch="$(uname -m)"; \
    case "${arch}" in \
        x86_64) target="x86_64-unknown-linux-musl"; checksum="${JUST_SHA256_X86_64}" ;; \
        aarch64) target="aarch64-unknown-linux-musl"; checksum="${JUST_SHA256_AARCH64}" ;; \
        *) echo "Unsupported architecture: ${arch}" >&2; exit 1 ;; \
    esac; \
    url="https://github.com/casey/just/releases/download/${JUST_VERSION}/just-${JUST_VERSION}-${target}.tar.gz"; \
    curl -fsSLo /tmp/just.tar.gz "${url}"; \
    echo "${checksum}  /tmp/just.tar.gz" | sha256sum -c -; \
    tar -xzf /tmp/just.tar.gz -C /tmp just; \
    install -m 0755 /tmp/just /usr/local/bin/just; \
    rm -f /tmp/just /tmp/just.tar.gz; \
    just --version; \
    fi

# Install Gitleaks from checksummed upstream release archives.
ARG GITLEAKS_ENABLED=1
ARG GITLEAKS_VERSION=8.30.1
ARG GITLEAKS_SHA256_X64=551f6fc83ea457d62a0d98237cbad105af8d557003051f41f3e7ca7b3f2470eb
ARG GITLEAKS_SHA256_ARM64=e4a487ee7ccd7d3a7f7ec08657610aa3606637dab924210b3aee62570fb4b080
RUN if [ "${GITLEAKS_ENABLED}" = "1" ]; then \
    set -eux; \
    arch="$(uname -m)"; \
    case "${arch}" in \
        x86_64) gitleaks_arch="x64"; checksum="${GITLEAKS_SHA256_X64}" ;; \
        aarch64) gitleaks_arch="arm64"; checksum="${GITLEAKS_SHA256_ARM64}" ;; \
        *) echo "Unsupported architecture: ${arch}" >&2; exit 1 ;; \
    esac; \
    url="https://github.com/gitleaks/gitleaks/releases/download/v${GITLEAKS_VERSION}/gitleaks_${GITLEAKS_VERSION}_linux_${gitleaks_arch}.tar.gz"; \
    curl -fsSLo /tmp/gitleaks.tar.gz "${url}"; \
    echo "${checksum}  /tmp/gitleaks.tar.gz" | sha256sum -c -; \
    mkdir -p /tmp/gitleaks-dist; \
    tar -xzf /tmp/gitleaks.tar.gz -C /tmp/gitleaks-dist gitleaks LICENSE; \
    install -m 0755 /tmp/gitleaks-dist/gitleaks /usr/local/bin/gitleaks; \
    install -d /usr/local/share/licenses/gitleaks; \
    install -m 0644 /tmp/gitleaks-dist/LICENSE /usr/local/share/licenses/gitleaks/LICENSE; \
    rm -rf /tmp/gitleaks-dist /tmp/gitleaks.tar.gz; \
    gitleaks version; \
    fi

# Install bat (cat clone with syntax highlighting) from GitHub releases.
ARG BAT_ENABLED=1
ARG BAT_VERSION=0.26.1
ARG BAT_SHA256_X64=0dcd8ac79732c0d5b136f11f4ee00e581440e16a44eab5b3105b611bbf2cf191
ARG BAT_SHA256_ARM64=6369242c584065f195fb20cb36fbd7cb63ae690605bbe89868a7596b596c2c23
RUN if [ "${BAT_ENABLED}" = "1" ]; then \
    set -eux; \
    arch="$(uname -m)"; \
    case "${arch}" in \
        x86_64) bat_arch="x86_64"; checksum="${BAT_SHA256_X64}" ;; \
        aarch64) bat_arch="aarch64"; checksum="${BAT_SHA256_ARM64}" ;; \
        *) echo "Unsupported architecture: ${arch}" >&2; exit 1 ;; \
    esac; \
    curl -fsSLo /tmp/bat.tar.gz "https://github.com/sharkdp/bat/releases/download/v${BAT_VERSION}/bat-v${BAT_VERSION}-${bat_arch}-unknown-linux-musl.tar.gz"; \
    echo "${checksum}  /tmp/bat.tar.gz" | sha256sum -c -; \
    mkdir -p /tmp/bat-dist; \
    tar -xzf /tmp/bat.tar.gz -C /tmp/bat-dist --strip-components=1; \
    install -m 0755 /tmp/bat-dist/bat /usr/local/bin/bat; \
    rm -rf /tmp/bat-dist /tmp/bat.tar.gz; \
    bat --version; \
    fi

# Install fd (fast find alternative) from GitHub releases.
ARG FD_ENABLED=1
ARG FD_VERSION=10.5.2
ARG FD_SHA256_X64=7e2d07fa2b8807642aaec67b7e2972a9fbe4db26fcb340a7372392db42b26694
ARG FD_SHA256_ARM64=63ea52cb31586e6d98efa2f06d73d542f16c7d0c4af0f07b579aaf9714cf907a
RUN if [ "${FD_ENABLED}" = "1" ]; then \
    set -eux; \
    arch="$(uname -m)"; \
    case "${arch}" in \
        x86_64) fd_arch="x86_64"; checksum="${FD_SHA256_X64}" ;; \
        aarch64) fd_arch="aarch64"; checksum="${FD_SHA256_ARM64}" ;; \
        *) echo "Unsupported architecture: ${arch}" >&2; exit 1 ;; \
    esac; \
    curl -fsSLo /tmp/fd.tar.gz "https://github.com/sharkdp/fd/releases/download/v${FD_VERSION}/fd-v${FD_VERSION}-${fd_arch}-unknown-linux-musl.tar.gz"; \
    echo "${checksum}  /tmp/fd.tar.gz" | sha256sum -c -; \
    mkdir -p /tmp/fd-dist; \
    tar -xzf /tmp/fd.tar.gz -C /tmp/fd-dist --strip-components=1; \
    install -m 0755 /tmp/fd-dist/fd /usr/local/bin/fd; \
    rm -rf /tmp/fd-dist /tmp/fd.tar.gz; \
    fd --version; \
    fi

# Install zk (Zettelkasten note-taking assistant) from GitHub releases.
ARG ZK_ENABLED=1
ARG ZK_VERSION=0.15.7
ARG ZK_SHA256_X64=9339cf4643159cfc80ee6b9c232abf84076ea154a057bf8926eb71cab37d3abe
ARG ZK_SHA256_ARM64=8404716171c04e131759feebb551e5946162732f20c178cc38099af10d0ce800
RUN if [ "${ZK_ENABLED}" = "1" ]; then \
    set -eux; \
    arch="$(uname -m)"; \
    case "${arch}" in \
        x86_64) zk_arch="amd64"; checksum="${ZK_SHA256_X64}" ;; \
        aarch64) zk_arch="arm64"; checksum="${ZK_SHA256_ARM64}" ;; \
        *) echo "Unsupported architecture: ${arch}" >&2; exit 1 ;; \
    esac; \
    curl -fsSLo /tmp/zk.tar.gz "https://github.com/zk-org/zk/releases/download/v${ZK_VERSION}/zk-v${ZK_VERSION}-linux-${zk_arch}.tar.gz"; \
    echo "${checksum}  /tmp/zk.tar.gz" | sha256sum -c -; \
    tar -xzf /tmp/zk.tar.gz -C /tmp; \
    install -m 0755 /tmp/zk /usr/local/bin/zk; \
    rm -f /tmp/zk /tmp/zk.tar.gz; \
    zk --version; \
    fi

# Install SecretSpec from checksummed upstream release archives.
ARG SECRETSPEC_ENABLED=0
ARG SECRETSPEC_VERSION=0.21.1
ARG SECRETSPEC_SHA256_X64=a4c4682edc873b4f75872e66f0753492e87eab0ea02e898b8f9405f7151a37c6
ARG SECRETSPEC_SHA256_ARM64=1cdbd62c9eb9500eab52a31d452290e34d998eb28f28074529f8faec76547e36
RUN if [ "${SECRETSPEC_ENABLED}" = "1" ]; then \
    set -eux; \
    arch="$(uname -m)"; \
    case "${arch}" in \
        x86_64) target="x86_64-unknown-linux-gnu"; checksum="${SECRETSPEC_SHA256_X64}" ;; \
        aarch64) target="aarch64-unknown-linux-gnu"; checksum="${SECRETSPEC_SHA256_ARM64}" ;; \
        *) echo "Unsupported architecture: ${arch}" >&2; exit 1 ;; \
    esac; \
    asset="secretspec-${target}.tar.xz"; \
    url="https://github.com/cachix/secretspec/releases/download/v${SECRETSPEC_VERSION}/${asset}"; \
    curl -fsSLo "/tmp/${asset}" "${url}"; \
    echo "${checksum}  /tmp/${asset}" | sha256sum -c -; \
    mkdir -p /tmp/secretspec-dist; \
    tar -xJf "/tmp/${asset}" -C /tmp/secretspec-dist --strip-components=1; \
    install -m 0755 /tmp/secretspec-dist/secretspec /usr/local/bin/secretspec; \
    install -d /usr/local/share/licenses/secretspec; \
    install -m 0644 /tmp/secretspec-dist/LICENSE \
        /usr/local/share/licenses/secretspec/LICENSE; \
    rm -f "/tmp/${asset}"; \
    rm -rf /tmp/secretspec-dist; \
    fi

# Install the selected Node.js LTS release and its bundled npm via nvm.
ARG NVM_VERSION=0.41.0
ARG NVM_SOURCE_SHA256=532560c9ecc6ef484279fcc1c600e9346537bc7913b891ffd0ec0caca5072694
ARG NODE_VERSION=26.13.1
ENV NVM_DIR=/usr/local/nvm
RUN set -eux; \
    mkdir -p "${NVM_DIR}"; \
    curl -fsSLo /tmp/nvm.tar.gz "https://codeload.github.com/nvm-sh/nvm/tar.gz/refs/tags/v${NVM_VERSION}"; \
    echo "${NVM_SOURCE_SHA256}  /tmp/nvm.tar.gz" | sha256sum -c -; \
    tar -xzf /tmp/nvm.tar.gz -C "${NVM_DIR}" --strip-components=1; \
    rm -f /tmp/nvm.tar.gz; \
    set +u; \
    . "${NVM_DIR}/nvm.sh"; \
    nvm install "${NODE_VERSION}"; \
    nvm alias default "${NODE_VERSION}"; \
    nvm use --silent default; \
    ln -sfn "$(dirname "$(dirname "$(command -v node)")")" "${NVM_DIR}/default"; \
    set -u; \
    chmod -R a+rX "${NVM_DIR}"; \
    node --version; \
    npm --version

# Install rustup and Rust toolchain from GitHub releases with SHA256 verification
ARG RUST_ENABLED=0
ARG RUSTUP_VERSION=1.29.3
ARG RUSTUP_SHA256_X64=b1c8cb14e30889e7e2999e6b69e62d9e9b9ffc0f4df8180564d306d9680e6c55
ARG RUSTUP_SHA256_ARM64=9f608c142e0e38a78957d0661ba1dfaf0b6fb37184cfaa4b9a0aa57af6184282
ARG RUST_VERSION=1.100.0
ARG CARGO_BINSTALL_VERSION=1.27.0
ARG CARGO_RUN_BIN_VERSION=1.7.5
ENV RUSTUP_HOME=/usr/local/rustup \
    CARGO_HOME=/usr/local/cargo \
    PATH=/usr/local/cargo/bin:$PATH
RUN if [ "${RUST_ENABLED}" = "1" ]; then \
    set -eux; \
    arch="$(uname -m)"; \
    case "${arch}" in \
        x86_64) rustup_arch="x86_64"; checksum="${RUSTUP_SHA256_X64}" ;; \
        aarch64) rustup_arch="aarch64"; checksum="${RUSTUP_SHA256_ARM64}" ;; \
        *) echo "Unsupported architecture: ${arch}" >&2; exit 1 ;; \
    esac; \
    url="https://static.rust-lang.org/rustup/archive/${RUSTUP_VERSION}/${rustup_arch}-unknown-linux-gnu/rustup-init"; \
    curl -fsSLo /tmp/rustup-init "${url}"; \
    echo "${checksum}  /tmp/rustup-init" | sha256sum -c -; \
    chmod +x /tmp/rustup-init; \
    /tmp/rustup-init -y --default-toolchain "${RUST_VERSION}" --profile minimal --no-modify-path; \
    rm -f /tmp/rustup-init; \
    rustup component add rust-analyzer rust-src rustfmt clippy; \
    rustup target add wasm32-unknown-unknown; \
    cargo install cargo-binstall --version "${CARGO_BINSTALL_VERSION}" --locked; \
    cargo install cargo-run-bin --version "${CARGO_RUN_BIN_VERSION}" --locked; \
    chmod -R a+rX $RUSTUP_HOME $CARGO_HOME; \
    rustc --version; \
    cargo --version; \
    cargo-binstall -V; \
    cargo bin --version; \
    fi

# Install PureScript tooling.
ARG PURESCRIPT_ENABLED=0
RUN if [ "${PURESCRIPT_ENABLED}" = "1" ]; then \
    . "${NVM_DIR}/nvm.sh"; \
    nvm use --silent default; \
    npm install -g purescript spago purs-tidy; \
    fi

# Install ghcup and Haskell toolchain (ghc, cabal, stack, hls, fourmolu, hlint)
# To update ghcup: change GHCUP_VERSION, then get SHA256s from:
#   https://downloads.haskell.org/~ghcup/<version>/SHA256SUMS
ARG HASKELL_ENABLED=0
ARG GHCUP_VERSION=0.2.6.2
ARG GHCUP_SHA256_X64=9ed5da5449b48043a0d17e767c05d2ef585e25a639bb934329496c6d2fad9cf8
ARG GHCUP_SHA256_ARM64=65a5f05120288ee4f1a81d28825374b6af317456a351a586adfce90c6dc29e3b
ARG GHC_VERSION=9.14.1
ARG CABAL_VERSION=3.18.2.0
ARG STACK_VERSION=3.11.1
ARG HLS_VERSION=2.15.0.0
ARG FOURMOLU_VERSION=0.21.0.0
ARG HLINT_VERSION=3.10
ARG HLINT_GHC_VERSION=9.12.4
ARG HLINT_SOURCE_SHA256=d99672337c06b455884ac14418d562701143141d0d7e46af476817c2ae3efe37
ENV GHCUP_INSTALL_BASE_PREFIX=/usr/local
RUN if [ "${HASKELL_ENABLED}" = "1" ]; then \
    set -eux; \
    mkdir -p /usr/local/.ghcup/bin; \
    arch="$(uname -m)"; \
    case "${arch}" in \
        x86_64) ghcup_arch="x86_64"; checksum="${GHCUP_SHA256_X64}" ;; \
        aarch64) ghcup_arch="aarch64"; checksum="${GHCUP_SHA256_ARM64}" ;; \
        *) echo "Unsupported architecture: ${arch}" >&2; exit 1 ;; \
    esac; \
    curl -fsSLo /tmp/ghcup "https://downloads.haskell.org/~ghcup/${GHCUP_VERSION}/${ghcup_arch}-linux-ghcup-${GHCUP_VERSION}"; \
    echo "${checksum}  /tmp/ghcup" | sha256sum -c -; \
    install -m 0755 /tmp/ghcup /usr/local/.ghcup/bin/ghcup; \
    rm -f /tmp/ghcup; \
    export PATH="/usr/local/.ghcup/bin:${PATH}"; \
    ghcup install ghc "${GHC_VERSION}" --set; \
    ghcup install cabal "${CABAL_VERSION}" --set; \
    ghcup install stack "${STACK_VERSION}" --set; \
    ghcup install hls "${HLS_VERSION}" --set; \
    ghcup config add-release-channel 3rdparty; \
    ghcup install fourmolu "${FOURMOLU_VERSION}"; \
    if [ "${arch}" = "aarch64" ]; then \
        ghcup install ghc "${HLINT_GHC_VERSION}"; \
        curl -fsSLo /tmp/hlint.tar.gz "https://hackage.haskell.org/package/hlint-${HLINT_VERSION}/hlint-${HLINT_VERSION}.tar.gz"; \
        echo "${HLINT_SOURCE_SHA256}  /tmp/hlint.tar.gz" | sha256sum -c -; \
        mkdir /tmp/hlint-source; \
        tar -xzf /tmp/hlint.tar.gz -C /tmp/hlint-source --strip-components=1; \
        export CABAL_DIR=/tmp/hlint-cabal; \
        export LC_ALL=C.utf8; \
        cabal update; \
        cd /tmp/hlint-source; \
        cabal install exe:hlint --installdir=/usr/local/.ghcup/bin --install-method=copy \
            --with-compiler="ghc-${HLINT_GHC_VERSION}" \
            --program-suffix="-${HLINT_VERSION}"; \
        cd /root; \
        rm -rf /tmp/hlint.tar.gz /tmp/hlint-source "${CABAL_DIR}"; \
        ghcup rm ghc "${HLINT_GHC_VERSION}"; \
    else \
        ghcup install hlint "${HLINT_VERSION}"; \
    fi; \
    ln -sf "/usr/local/.ghcup/bin/fourmolu-${FOURMOLU_VERSION}" /usr/local/bin/fourmolu; \
    ln -sf "/usr/local/.ghcup/bin/hlint-${HLINT_VERSION}" /usr/local/bin/hlint; \
    fourmolu --version; \
    hlint --version; \
    fi

# Install wasm32-wasi GHC toolchain separately so native ghc/cabal remain the defaults.
# The wasm toolchain is installed by ghc-wasm-meta and provides wasm32-wasi-ghc,
# wasm32-wasi-cabal, wasmtime, binaryen, and WASI SDK tools.
ARG WASM_GHC_ENABLED=0
ARG WASM_GHC_FLAVOUR=9.14
ARG WASM_GHC_META_REF=master
ENV GHC_WASM_PREFIX=/opt/ghc-wasm
RUN if [ "${WASM_GHC_ENABLED}" = "1" ]; then \
    set -eux; \
    git clone --depth 1 --branch "${WASM_GHC_META_REF}" https://github.com/haskell-wasm/ghc-wasm-meta.git /tmp/ghc-wasm-meta; \
    FLAVOUR="${WASM_GHC_FLAVOUR}" PREFIX="${GHC_WASM_PREFIX}" /tmp/ghc-wasm-meta/setup.sh; \
    rm -rf /tmp/ghc-wasm-meta; \
    chmod -R a+rX "${GHC_WASM_PREFIX}"; \
    chmod -R a+rwX "${GHC_WASM_PREFIX}/.cabal"; \
    . "${GHC_WASM_PREFIX}/env"; \
    wasm32-wasi-ghc --version; \
    wasm32-wasi-cabal --version; \
    wasmtime --version; \
    fi

# Install Rocq prover and command-line tools via opam.
ARG ROCQ_ENABLED=0
ARG ROCQ_OCAML_VERSION=5.5.0
ARG OPAM_VERSION=2.5.2
ENV OPAMROOT=/opt/opam
RUN if [ "${ROCQ_ENABLED}" = "1" ]; then \
    set -eux; \
    microdnf -y --setopt=install_weak_deps=0 install m4 perl bubblewrap clang; \
    arch="$(uname -m)"; \
    case "${arch}" in \
        x86_64) opam_arch="x86_64"; checksum="edfca2630c373b44b7ee1c2f81cd8dcf67468d0db57d6c02158de553ac63dbd4" ;; \
        aarch64) opam_arch="arm64"; checksum="c4106ece84bcb60c68342573d2d6b4f0d6770ee088015c2216adc83d8854dcf9" ;; \
        *) echo "Unsupported architecture: ${arch}" >&2; exit 1 ;; \
    esac; \
    curl -fsSLo /tmp/opam "https://github.com/ocaml/opam/releases/download/${OPAM_VERSION}/opam-${OPAM_VERSION}-${opam_arch}-linux"; \
    echo "${checksum}  /tmp/opam" | sha256sum -c -; \
    install -m 0755 /tmp/opam /usr/local/bin/opam; \
    rm -f /tmp/opam; \
    opam init --bare --disable-sandboxing --no-setup --yes; \
    fi
RUN if [ "${ROCQ_ENABLED}" = "1" ]; then \
    set -eux; \
    opam switch create rocq "ocaml-base-compiler.${ROCQ_OCAML_VERSION}" --yes; \
    eval "$(opam env --switch=rocq --set-switch)"; \
    opam repo add rocq-released https://rocq-prover.org/opam/released --yes; \
    opam update --yes; \
    fi
ARG ROCQ_VERSION=9.2.0
ARG VSROCQ_LANGUAGE_SERVER_PACKAGE=vsrocq-language-server
ARG ROCQ_EXTRA_PACKAGES="rocq-equations.1.3.2+9.2 coq-quickchick.2.2.0 coq-ext-lib.0.13.1 coq-hammer.1.3.3+9.2 coq-hammer-tactics.1.3.3+9.2"
RUN if [ "${ROCQ_ENABLED}" = "1" ]; then \
    set -eux; \
    opam install --switch=rocq --yes "rocq-prover.${ROCQ_VERSION}" "${VSROCQ_LANGUAGE_SERVER_PACKAGE}" ${ROCQ_EXTRA_PACKAGES}; \
    opam clean --all --yes; \
    chmod -R a+rX "${OPAMROOT}"; \
    ln -sf "${OPAMROOT}/rocq/bin/rocq" /usr/local/bin/rocq; \
    ln -sf "${OPAMROOT}/rocq/bin/rocqchk" /usr/local/bin/rocqchk; \
    ln -sf "${OPAMROOT}/rocq/bin/vsrocqtop" /usr/local/bin/vsrocqtop; \
    rocq --version; \
    command -v vsrocqtop; \
    fi

# Install SMT solver tooling from GitHub releases.
ARG SMT_ENABLED=0
ARG CVC5_VERSION=1.4.2
ARG CVC5_SHA256_X64=7eb18f8c814c36a46c5a7d003983e9cfbc4b0a9828d6dd596239291bd4cc61d8
ARG CVC5_SHA256_ARM64=765ebee59d9e5efccb60a445fa66fbddfb07a8de9fe7a5b6d128e5c2aafec974
RUN if [ "${SMT_ENABLED}" = "1" ]; then \
    set -eux; \
    arch="$(uname -m)"; \
    case "${arch}" in \
        x86_64) asset="cvc5-Linux-x86_64-static.zip"; checksum="${CVC5_SHA256_X64}" ;; \
        aarch64) asset="cvc5-Linux-arm64-static.zip"; checksum="${CVC5_SHA256_ARM64}" ;; \
        *) echo "Unsupported architecture: ${arch}" >&2; exit 1 ;; \
    esac; \
    curl -fsSLo "/tmp/${asset}" "https://github.com/cvc5/cvc5/releases/download/cvc5-${CVC5_VERSION}/${asset}"; \
    echo "${checksum}  /tmp/${asset}" | sha256sum -c -; \
    unzip -q "/tmp/${asset}" -d /opt; \
    mv "/opt/${asset%.zip}" "/opt/cvc5-${CVC5_VERSION}"; \
    ln -sf "/opt/cvc5-${CVC5_VERSION}/bin/cvc5" /usr/local/bin/cvc5; \
    rm -f "/tmp/${asset}"; \
    cvc5 --version; \
    fi

# Setup home
ARG PROJECT_NAME=workspace
RUN chown -R user:user /home/user \
    && if [ -d /usr/local/.ghcup/logs ]; then chmod -R a+rwX /usr/local/.ghcup/logs; fi \
    && install -d -o user -g user \
      /home/user/.local/bin /home/user/.local/share /home/user/.local/state \
      /home/user/.cache /home/user/.cargo /home/user/.config \
      /home/user/.claude /home/user/.codex /home/user/.gemini \
      /home/user/.config/opencode /home/user/.local/share/opencode \
      "/workspaces/${PROJECT_NAME}/.glo"

VOLUME ["/home/user/.config", "/home/user/.local/share"]

# Install Claude CLI from official releases
# To update Claude Code: change CLAUDE_VERSION, then run:
#   release_base="https://downloads.claude.ai/claude-code-releases"
#   curl -fsSL "$release_base/VERSION/linux-x64/claude" | sha256sum    # for CLAUDE_SHA256_X64
#   curl -fsSL "$release_base/VERSION/linux-arm64/claude" | sha256sum  # for CLAUDE_SHA256_ARM64
ARG CLAUDE_ENABLED=0
ARG CLAUDE_VERSION=2.1.327
ARG CLAUDE_SHA256_X64=343c744baa14bfd38286a7cb90871051f04379956da6c5b803a9e66019a76ac9
ARG CLAUDE_SHA256_ARM64=acf0ef2f9da8d5ab08f193f007e19a06cbfb608b96a2f1f758d63a92a386cff8
RUN if [ "${CLAUDE_ENABLED}" = "1" ]; then \
    set -eux; \
    arch="$(uname -m)"; \
    case "${arch}" in \
        x86_64) claude_arch="x64"; checksum="${CLAUDE_SHA256_X64}" ;; \
        aarch64) claude_arch="arm64"; checksum="${CLAUDE_SHA256_ARM64}" ;; \
        *) echo "Unsupported architecture: ${arch}" >&2; exit 1 ;; \
    esac; \
    release_base="https://downloads.claude.ai/claude-code-releases"; \
    platform="linux-${claude_arch}"; \
    url="$release_base/${CLAUDE_VERSION}/$platform/claude"; \
    binary_path="/tmp/claude"; \
    curl -fsSL -o "$binary_path" "$url"; \
    echo "$checksum  $binary_path" | sha256sum -c -; \
    install -d -o user -g user /home/user/.local /home/user/.local/bin; \
    install -m 0755 -o user -g user "$binary_path" /home/user/.local/bin/claude; \
    rm -rf "$binary_path"; \
    fi

# Install gemini
ARG GEMINI_ENABLED=0
RUN if [ "${GEMINI_ENABLED}" = "1" ]; then \
    . "${NVM_DIR}/nvm.sh"; \
    nvm use --silent default; \
    npm install -g \
      @google/gemini-cli@0.68.0; \
    fi

# Install codex
ARG CODEX_ENABLED=0
RUN if [ "${CODEX_ENABLED}" = "1" ]; then \
    . "${NVM_DIR}/nvm.sh"; \
    nvm use --silent default; \
    npm install -g \
      @openai/codex@0.170.0; \
    fi

# Install opencode
ARG OPENCODE_ENABLED=0
RUN if [ "${OPENCODE_ENABLED}" = "1" ]; then \
    . "${NVM_DIR}/nvm.sh"; \
    nvm use --silent default; \
    npm install -g \
      opencode-ai@1.19.6; \
    fi

# Install glo
COPY files/glo/ /opt/glo/
RUN UV_PROJECT_ENVIRONMENT=/opt/glo/.venv \
    uv sync --project /opt/glo/lib/build --package glo_build --frozen \
        --python /opt/python/bin/python3 \
    && chown -R user:user /opt/glo

USER user
WORKDIR /home/user

ENV UV_SYSTEM_PYTHON=1 \
    CARGO_HOME=/home/user/.cargo \
    PIP_DISABLE_PIP_VERSION_CHECK=on \
    NODE_PATH="/opt/ghc-wasm/nodejs/lib/node_modules" \
    PATH="/home/user/.local/bin:/opt/glo/bin:/opt/ghc-wasm/wasm-run/bin:/opt/ghc-wasm/wasm32-wasi-cabal/bin:/opt/ghc-wasm/wasmtime/bin:/opt/ghc-wasm/binaryen/bin:/opt/ghc-wasm/wasi-sdk/bin:/opt/ghc-wasm/wasm32-wasi-ghc/bin:/usr/local/nvm/default/bin:/usr/local/.ghcup/bin:/usr/local/ghcup/bin:/usr/local/cargo/bin:/usr/local/bin:${PATH}"

CMD ["/bin/bash"]

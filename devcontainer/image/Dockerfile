FROM rockylinux/rockylinux:10-minimal

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
        pv \
        pkgconf-pkg-config \
        procps-ng \
        psmisc \
        python3.12 \
        python3.12-pip \
        readline \
        rsync \
        ripgrep \
        shellcheck \
        sqlite \
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
        libpq-devel \
        postgresql \
        postgresql-server \
        gmp-devel \
        libffi-devel \
        zlib-devel

# Upgrade pip and install uv
RUN python3 -m pip install --no-cache-dir --upgrade pip \
    && python3 -m pip install --no-cache-dir uv

# Install just from GitHub releases.
ARG JUST_ENABLED=1
ARG JUST_VERSION=1.43.0
ARG JUST_SHA256_X86_64=a1bc93654f31669fd964ea3011a5e5e9676b9b6f8adcd762606e5140632ea72d
ARG JUST_SHA256_AARCH64=4fcd8310081c32742eb984b1fdd0eee2e5d4d0f1be9629318012d42606ec9b3e
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

# Install bat (cat clone with syntax highlighting) from GitHub releases.
ARG BAT_ENABLED=1
ARG BAT_VERSION=0.26.0
ARG BAT_SHA256_X64=26a683b038fbc526c6df4166db693ddc9e431e5bdc285d45ccd6b72f3cff5ffd
ARG BAT_SHA256_ARM64=6ee11bd8a520c514e230669156d9298f0dd2b5afc788c0952a4b14fcec51eaee
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
ARG FD_VERSION=10.3.0
ARG FD_SHA256_X64=2b6bfaae8c48f12050813c2ffe1884c61ea26e750d803df9c9114550a314cd14
ARG FD_SHA256_ARM64=996b9b1366433b211cb3bbedba91c9dbce2431842144d925428ead0adf32020b
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
ARG ZK_VERSION=0.15.1
ARG ZK_SHA256_X64=6d652bba16faccd169469ceddf3b1e1dd8f3b2af72de218b0f9921809139c0b4
ARG ZK_SHA256_ARM64=19460e19e3389220015aa98ca849449d9c739ffd6f45c1935b0cd2d149424ce5
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

# Install Node.js via nvm using the latest LTS line.
ARG NVM_VERSION=0.40.3
ENV NVM_DIR=/usr/local/nvm
RUN set -eux; \
    mkdir -p "${NVM_DIR}"; \
    curl -fsSLo /tmp/install-nvm.sh "https://raw.githubusercontent.com/nvm-sh/nvm/v${NVM_VERSION}/install.sh"; \
    bash /tmp/install-nvm.sh; \
    rm -f /tmp/install-nvm.sh; \
    set +u; \
    . "${NVM_DIR}/nvm.sh"; \
    nvm install --lts; \
    nvm alias default 'lts/*'; \
    nvm use --silent --lts; \
    ln -sfn "$(dirname "$(dirname "$(command -v node)")")" "${NVM_DIR}/default"; \
    set -u; \
    chmod -R a+rX "${NVM_DIR}"; \
    node --version; \
    npm --version

# Install rustup and Rust toolchain from GitHub releases with SHA256 verification
ARG RUST_ENABLED=0
ARG RUSTUP_VERSION=1.29.0
ARG RUSTUP_SHA256_X64=4acc9acc76d5079515b46346a485974457b5a79893cfb01112423c89aeb5aa10
ARG RUSTUP_SHA256_ARM64=9732d6c5e2a098d3521fca8145d826ae0aaa067ef2385ead08e6feac88fa5792
ARG RUST_VERSION=1.95.0
ARG CARGO_BINSTALL_VERSION=1.19.1
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
    nvm use --silent --lts; \
    npm install -g purescript spago purs-tidy; \
    fi

# Install ghcup and Haskell toolchain (ghc, cabal, stack, hls, ormolu, hlint)
# To update ghcup: change GHCUP_VERSION, then get SHA256s from:
#   https://downloads.haskell.org/~ghcup/<version>/SHA256SUMS
ARG HASKELL_ENABLED=0
ARG GHCUP_VERSION=0.2.2.0
ARG GHCUP_SHA256_X64=29c7ed853a0525e6d787697ebb12b0a76f2ab0c5aca3e0b23e5ba75279ddd19d
ARG GHCUP_SHA256_ARM64=67d50a72e33454d566c9e40db2d64b289ce3deaaee781633dc4a25e4a696a319
ARG GHC_VERSION=9.12.4
ARG CABAL_VERSION=3.16.1.0
ARG STACK_VERSION=3.9.3
ARG HLS_VERSION=2.14.0.0
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
    ghcup install ormolu; \
    ghcup install hlint; \
    ln -sf /usr/local/.ghcup/bin/ormolu-* /usr/local/bin/ormolu; \
    ln -sf /usr/local/.ghcup/bin/hlint-* /usr/local/bin/hlint; \
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

# Setup home
ARG PROJECT_NAME=workspace
RUN groupadd --gid 1000 user \
    && useradd --uid 1000 --gid 1000 --create-home --shell /bin/bash user \
    && chown -R user:user /home/user \
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
#   gcs_bucket="https://storage.googleapis.com/claude-code-dist-86c565f3-f756-42ad-8dfa-d59b1c096819/claude-code-releases"
#   curl -fsSL "$gcs_bucket/VERSION/linux-x64/claude" | sha256sum    # for CLAUDE_SHA256_X64
#   curl -fsSL "$gcs_bucket/VERSION/linux-arm64/claude" | sha256sum  # for CLAUDE_SHA256_ARM64
ARG CLAUDE_ENABLED=0
ARG CLAUDE_VERSION=2.1.170
ARG CLAUDE_SHA256_X64=849e007277a0442ab27570d3e3d6d43787507946590e8dd1947e5a39b7081f9e
ARG CLAUDE_SHA256_ARM64=1bb9d032440a75532f7dd4cafbc687f220aaf16c63eba17e192dfbec2f04bd25
RUN if [ "${CLAUDE_ENABLED}" = "1" ]; then \
    set -eux; \
    arch="$(uname -m)"; \
    case "${arch}" in \
        x86_64) claude_arch="x64"; checksum="${CLAUDE_SHA256_X64}" ;; \
        aarch64) claude_arch="arm64"; checksum="${CLAUDE_SHA256_ARM64}" ;; \
        *) echo "Unsupported architecture: ${arch}" >&2; exit 1 ;; \
    esac; \
    gcs_bucket="https://storage.googleapis.com/claude-code-dist-86c565f3-f756-42ad-8dfa-d59b1c096819/claude-code-releases"; \
    platform="linux-${claude_arch}"; \
    url="$gcs_bucket/${CLAUDE_VERSION}/$platform/claude"; \
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
    nvm use --silent --lts; \
    npm install -g \
      @google/gemini-cli@0.49.0; \
    fi

# Install codex
ARG CODEX_ENABLED=0
RUN if [ "${CODEX_ENABLED}" = "1" ]; then \
    . "${NVM_DIR}/nvm.sh"; \
    nvm use --silent --lts; \
    npm install -g \
      @openai/codex@0.142.4; \
    fi

# Install opencode
ARG OPENCODE_ENABLED=0
RUN if [ "${OPENCODE_ENABLED}" = "1" ]; then \
    . "${NVM_DIR}/nvm.sh"; \
    nvm use --silent --lts; \
    npm install -g \
      opencode-ai@1.17.11; \
    fi

# Install glo
RUN mkdir -p /opt/glo/bin /opt/glo/lib
COPY files/glo/README.md /opt/glo/README.md
COPY --chmod=0755 files/glo/bin/glo /opt/glo/bin/glo
COPY --chmod=0755 files/glo/bin/glo-agent /opt/glo/bin/glo-agent
COPY --chmod=0755 files/glo/bin/glo-gen /opt/glo/bin/glo-gen
COPY --chmod=0755 files/glo/bin/glo-local /opt/glo/bin/glo-local
COPY --chmod=0755 files/glo/bin/glo-notes /opt/glo/bin/glo-notes
COPY --chmod=0755 files/glo/bin/glo-issue /opt/glo/bin/glo-issue
COPY --chmod=0755 files/glo/bin/glo-build /opt/glo/bin/glo-build
COPY --chmod=0755 files/glo/bin/glo-opencode /opt/glo/bin/glo-opencode
COPY --chmod=0755 files/glo/bin/glo-cargo-run-bin /opt/glo/bin/glo-cargo-run-bin
COPY files/glo/lib/ /opt/glo/lib/
COPY files/glo/templates/ /opt/glo/templates/
COPY files/glo/base-scaffold/ /opt/glo/base-scaffold/
RUN UV_PYTHON_INSTALL_DIR=/opt/glo/python \
    UV_PROJECT_ENVIRONMENT=/opt/glo/.venv \
    uv sync --project /opt/glo/lib/build --package glo_build --frozen
RUN chown -R user:user /opt/glo

USER user
WORKDIR /home/user

ENV UV_SYSTEM_PYTHON=1 \
    CARGO_HOME=/home/user/.cargo \
    PIP_DISABLE_PIP_VERSION_CHECK=on \
    NODE_PATH="/opt/ghc-wasm/nodejs/lib/node_modules" \
    PATH="/home/user/.local/bin:/opt/glo/bin:/opt/ghc-wasm/wasm-run/bin:/opt/ghc-wasm/wasm32-wasi-cabal/bin:/opt/ghc-wasm/wasmtime/bin:/opt/ghc-wasm/binaryen/bin:/opt/ghc-wasm/wasi-sdk/bin:/opt/ghc-wasm/wasm32-wasi-ghc/bin:/usr/local/nvm/default/bin:/usr/local/.ghcup/bin:/usr/local/ghcup/bin:/usr/local/cargo/bin:/usr/local/bin:${PATH}"

CMD ["/bin/bash"]

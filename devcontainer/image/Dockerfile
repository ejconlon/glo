FROM rockylinux/rockylinux:10-minimal AS base

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
        gmp-devel \
        libffi-devel \
        zlib-devel

# Install an explicit PostgreSQL 18 client, server, and development boundary.
# The default image contains no PostgreSQL packages or initialized cluster.
FROM base AS postgres-feature
ARG POSTGRES_ENABLED=0
ARG PGDG_REPO_RPM_VERSION=42.0-66
ARG PGDG_REPO_SHA256_X64=47cc6e0243230a0ebe79552ed932688ce58552bbc570e19b0888b3e8c88a66c7
ARG PGDG_REPO_SHA256_ARM64=a5c3355fb7667ccbba2d0f31ada02a658101ebdfe4aa384317070d9ae1890c31
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
        "https://download.postgresql.org/pub/repos/yum/reporpms/EL-10-${repo_arch}/${repo_rpm}"; \
    echo "${checksum}  /tmp/${repo_rpm}" | sha256sum -c -; \
    rpm --install "/tmp/${repo_rpm}"; \
    microdnf -y --setopt=install_weak_deps=0 install \
        libpq5-devel \
        postgresql18 \
        postgresql18-server; \
    rm -f "/tmp/${repo_rpm}"; \
    /usr/pgsql-18/bin/psql --version | grep -E '^psql \(PostgreSQL\) 18\.'; \
    fi

RUN groupadd --gid 1000 user \
    && useradd --uid 1000 --gid 1000 --create-home --shell /bin/bash user
COPY --chmod=0755 files/glo/bin/glo-postgres /usr/local/bin/glo-postgres
ENV PATH="/usr/pgsql-18/bin:${PATH}"

FROM postgres-feature AS development

# Upgrade pip and install uv
RUN python3 -m pip install --no-cache-dir --upgrade pip \
    && python3 -m pip install --no-cache-dir uv

# Install just from GitHub releases.
ARG JUST_ENABLED=1
ARG JUST_VERSION=1.58.0
ARG JUST_SHA256_X86_64=4a5cc2f53e6f0f8c59092a6cc38291eb729d46a7dd95d3ae582008881b84931d
ARG JUST_SHA256_AARCH64=748237128c4c40cbdabc65e841d05ceba13cc23a91eaba395495894c1d9764df
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
ARG FD_VERSION=10.4.2
ARG FD_SHA256_X64=e3257d48e29a6be965187dbd24ce9af564e0fe67b3e73c9bdcd180f4ec11bdde
ARG FD_SHA256_ARM64=f32d3657473fba74e2600babc8db0b93420d51169223b7e8143b2ed55d8fd9e8
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
ARG ZK_VERSION=0.15.6
ARG ZK_SHA256_X64=50b2f0a8c533d607e5a8a1f478fe78d5585317178bd86456659c049965a8945d
ARG ZK_SHA256_ARM64=80550e5ab50b826fef660e72fc6c7c8c872ad8673ffb798dabc32c714f63fdd5
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
ARG SECRETSPEC_VERSION=0.19.1
ARG SECRETSPEC_SHA256_X64=9a0b5882532f5ffbb1c687d9284fa8041949962b05f14fc131050f86c70e1efc
ARG SECRETSPEC_SHA256_ARM64=9b0804932f011ee13709d06a342cd7d30222a764bb62d343771964471b2a7e25
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

# Install Node.js via nvm using the latest LTS line.
ARG NVM_VERSION=0.40.6
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
ARG RUST_VERSION=1.97.1
ARG CARGO_BINSTALL_VERSION=1.21.1
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
ARG GHCUP_VERSION=0.2.6.2
ARG GHCUP_SHA256_X64=9ed5da5449b48043a0d17e767c05d2ef585e25a639bb934329496c6d2fad9cf8
ARG GHCUP_SHA256_ARM64=65a5f05120288ee4f1a81d28825374b6af317456a351a586adfce90c6dc29e3b
ARG GHC_VERSION=9.14.1
ARG CABAL_VERSION=3.16.1.0
ARG STACK_VERSION=3.11.1
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
ARG Z3_VERSION=5.0.0
ARG Z3_SHA256_X64=d4922cebc9f0a55629231ec0c62f0bbedf8006eddaed4e68199ad19626b697f6
ARG Z3_SHA256_ARM64=c9437ff7e419e715db76d20e4b2142bf60a206c8e1d2b380c0ce35dc8d07b1f4
RUN if [ "${SMT_ENABLED}" = "1" ]; then \
    set -eux; \
    arch="$(uname -m)"; \
    case "${arch}" in \
        x86_64) asset="z3-${Z3_VERSION}-x64-glibc-2.39.zip"; checksum="${Z3_SHA256_X64}" ;; \
        aarch64) asset="z3-${Z3_VERSION}-arm64-glibc-2.38.zip"; checksum="${Z3_SHA256_ARM64}" ;; \
        *) echo "Unsupported architecture: ${arch}" >&2; exit 1 ;; \
    esac; \
    curl -fsSLo "/tmp/${asset}" "https://github.com/Z3Prover/z3/releases/download/z3-${Z3_VERSION}/${asset}"; \
    echo "${checksum}  /tmp/${asset}" | sha256sum -c -; \
    unzip -q "/tmp/${asset}" -d /opt; \
    mv "/opt/${asset%.zip}" "/opt/z3-${Z3_VERSION}"; \
    ln -sf "/opt/z3-${Z3_VERSION}/bin/z3" /usr/local/bin/z3; \
    rm -f "/tmp/${asset}"; \
    z3 --version; \
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
ARG CLAUDE_VERSION=2.1.227
ARG CLAUDE_SHA256_X64=6832dc3f1797b890b71116e5f2dbbf9a83fd3d0498c235b4b0f9cd0e6e499ad6
ARG CLAUDE_SHA256_ARM64=db47335532cbcab67a4b3ab16d8f3f77976bf85d53c7d79f8296538aa22bfce6
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
    nvm use --silent --lts; \
    npm install -g \
      @google/gemini-cli@0.54.4; \
    fi

# Install codex
ARG CODEX_ENABLED=0
RUN if [ "${CODEX_ENABLED}" = "1" ]; then \
    . "${NVM_DIR}/nvm.sh"; \
    nvm use --silent --lts; \
    npm install -g \
      @openai/codex@0.147.0; \
    fi

# Install opencode
ARG OPENCODE_ENABLED=0
RUN if [ "${OPENCODE_ENABLED}" = "1" ]; then \
    . "${NVM_DIR}/nvm.sh"; \
    nvm use --silent --lts; \
    npm install -g \
      opencode-ai@1.18.16; \
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
COPY --chmod=0755 files/glo/bin/glo-secrets /opt/glo/bin/glo-secrets
COPY --chmod=0755 files/glo/bin/glo-postgres /opt/glo/bin/glo-postgres
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

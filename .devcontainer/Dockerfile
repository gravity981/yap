# Reads the Playwright version pinned in package-lock.json. A separate stage, so the
# browser layer below is rebuilt only when that version changes, not on every
# change of the frontend dependencies.
FROM mcr.microsoft.com/devcontainers/python:3.15 AS playwright-version
COPY frontend/package-lock.json /tmp/package-lock.json
RUN python -c "import json; print(json.load(open('/tmp/package-lock.json'))['packages']['node_modules/@playwright/test']['version'])" > /tmp/playwright-version

FROM mcr.microsoft.com/devcontainers/python:3.15

# Project virtual env, baked into the image
ENV VIRTUAL_ENV=/opt/venv
RUN python -m venv $VIRTUAL_ENV && chown -R vscode:vscode $VIRTUAL_ENV
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

# Login shells run /etc/profile.d/00-restore-env.sh, which puts the system
# Python ahead of the venv; re-prepend the venv afterwards
RUN echo 'export PATH="$VIRTUAL_ENV/bin:$PATH"' > /etc/profile.d/99-venv.sh

# Mount point for the shared claude-config volume, owned by vscode so the
# empty volume inherits that ownership on first mount
RUN mkdir -p /home/vscode/.claude && chown vscode:vscode /home/vscode/.claude

# Mount point for the dev database volume, same ownership trick
RUN mkdir -p /var/lib/yap && chown vscode:vscode /var/lib/yap

# Node.js, same major version as CI. Installed here rather than as a devcontainer
# feature, because the Playwright browser below needs node while the image is built.
ARG NODE_VERSION=26.12.0
RUN case "$(dpkg --print-architecture)" in \
        amd64) arch=x64 ;; \
        arm64) arch=arm64 ;; \
        *) echo "unsupported architecture" >&2; exit 1 ;; \
    esac \
    && archive="node-v${NODE_VERSION}-linux-${arch}.tar.xz" \
    && cd /tmp \
    && curl -fsSLO "https://nodejs.org/dist/v${NODE_VERSION}/${archive}" \
    && curl -fsSL "https://nodejs.org/dist/v${NODE_VERSION}/SHASUMS256.txt" | grep " ${archive}\$" | sha256sum -c - \
    && tar -xJf "${archive}" -C /usr/local --strip-components=1 --no-same-owner \
    && rm "${archive}" \
    && node --version && npm --version

# Chromium for the end-to-end tests, in the Playwright version pinned in
# package-lock.json, with its system libraries
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
COPY --from=playwright-version /tmp/playwright-version /tmp/playwright-version
RUN npx --yes "playwright@$(cat /tmp/playwright-version)" install --with-deps chromium \
    && chmod -R a+rX /ms-playwright \
    && rm -rf /root/.npm /tmp/playwright-version

# Backend dependencies (runtime + dev) from pyproject.toml. The package itself is
# not installed: pytest puts backend on the path, so code runs from the workspace.
COPY --chown=vscode:vscode backend/pyproject.toml /tmp/backend/pyproject.toml
USER vscode
RUN python -c "import tomllib; p = tomllib.load(open('/tmp/backend/pyproject.toml', 'rb'))['project']; print('\n'.join(p['dependencies'] + p['optional-dependencies']['dev']))" > /tmp/backend/requirements.txt \
    && pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r /tmp/backend/requirements.txt
USER root

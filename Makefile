.DEFAULT_GOAL := all
VERSION := $(shell grep -m 1 version pyproject.toml | tr -s ' ' | tr -d '"' | tr -d "'" | cut -d' ' -f3)
PACKAGE := $(shell grep -m 1 name pyproject.toml | tr -s ' ' | tr -d '"' | tr -d "'" | cut -d' ' -f3)
FW_VERSION := 2.15.1.1189
FW_DATA := wVbHkgKisg-

ifeq ($(OS),Windows_NT)
	SHELL := C:\Windows\System32\bash.exe
	ifeq ($(VENV_BIN_ACTIVATE),)
		VENV_BIN_ACTIVATE := .venv/Scripts/activate
	endif
	CODEXCTL := https://github.com/Jayy001/codexctl/releases/download/1717461181/windows-latest.zip
	CODEXCTL_HASH := 987c1eef9cd6093934c67f91e327eaf08e5bcad326b0168969ef1e76db39a1f3
	CODEXCTL_BIN := .venv/Scripts/codexctl.bin
else
	SHELL := /bin/bash
	ifeq ($(VENV_BIN_ACTIVATE),)
		VENV_BIN_ACTIVATE := .venv/bin/activate
	endif
	ifeq ($(OS),Darwin)
		CODEXCTL := https://github.com/Jayy001/codexctl/releases/download/1717461181/macos-latest.zip
		CODEXCTL_HASH := c2f91d6f2faf86c4b4d9917c7d5027819acbc949e55c09bf464765fd875d9818
	else
		CODEXCTL := https://github.com/Jayy001/codexctl/releases/download/1717461181/ubuntu-latest.zip
		CODEXCTL_HASH := 22caf38a55056f66f0a74222ebed3a00b5a13df1ace0d2489fa395c7beafbf1f
	endif
	CODEXCTL_BIN := .venv/bin/codexctl.bin
endif

PROTO_SOURCE := $(wildcard protobuf/*.proto)
PROTO_OBJ := $(addprefix $(PACKAGE),$(PROTO_SOURCE:%.proto=%_pb2.py))

OBJ := $(wildcard ${PACKAGE}/**)
OBJ += requirements.txt
OBJ += pyproject.toml
OBJ += README.md
OBJ += $(PROTO_OBJ)

define PLATFORM_SCRIPT
from sysconfig import get_platform
print(get_platform().replace('-', '_'), end="")
endef
export PLATFORM_SCRIPT
PLATFORM := $(shell python -c "$$PLATFORM_SCRIPT")

define ABI_SCRIPT
def main():
    try:
        from wheel.pep425tags import get_abi_tag
        print(get_abi_tag(), end="")
        return
    except ModuleNotFoundError:
        pass

    try:
        from wheel.vendored.packaging import tags
    except ModuleNotFoundError:
        from packaging import tags

    name=tags.interpreter_name()
    version=tags.interpreter_version()
    print(f"{name}{version}", end="")

main()
endef
export ABI_SCRIPT
ABI := $(shell python -c "$$ABI_SCRIPT")

clean:
	if [ -d .venv/mnt ] && mountpoint -q .venv/mnt; then \
		umount -ql .venv/mnt; \
	fi
	git clean --force -dX

build: wheel

release: wheel sdist

install: wheel
	if type pipx > /dev/null; then \
	    pipx install \
	        --force \
	        dist/${PACKAGE}-${VERSION}-${ABI}-${ABI}-${PLATFORM}.whl; \
	else \
	    pip install \
	        --user \
	        --force-reinstall \
	        --no-index \
	        --find-links=dist \
	        ${PACKAGE}; \
	fi

sdist: dist/${PACKAGE}-${VERSION}.tar.gz

wheel: dist/${PACKAGE}-${VERSION}-${ABI}-${ABI}-${PLATFORM}.whl

dist:
	mkdir -p dist

dist/${PACKAGE}-${VERSION}.tar.gz: dist $(OBJ)
	python -m build --sdist

dist/${PACKAGE}-${VERSION}-${ABI}-${ABI}-${PLATFORM}.whl: dist $(OBJ)
	python -m build --wheel

${VENV_BIN_ACTIVATE}: requirements.txt
	@echo "Setting up development virtual env in .venv"
	python -m venv .venv
	. ${VENV_BIN_ACTIVATE}; \
	python -m pip install --extra-index-url=https://wheels.eeems.codes/ -r requirements.txt


.venv/codexctl.zip: ${VENV_BIN_ACTIVATE}
	curl -L "${CODEXCTL}" -o .venv/codexctl.zip

${CODEXCTL_BIN}: .venv/codexctl.zip
	echo "${SHELL}"
	@bash -c 'if ! sha256sum -c <(echo "${CODEXCTL_HASH} .venv/codexctl.zip") > /dev/null 2>&1; then \
	    echo "Hash mismatch, removing invalid codexctl.zip"; \
	    rm .venv/codexctl.zip; \
	    exit 1; \
	fi'
	bash -c "unzip -n .venv/codexctl.zip -d .venv/bin"
	chmod +x ${CODEXCTL_BIN}

.venv/${FW_VERSION}_reMarkable2-${FW_DATA}.signed: ${CODEXCTL_BIN}
	${CODEXCTL_BIN} download --out .venv ${FW_VERSION}


$(PROTO_OBJ): $(PROTO_SOURCE)
	protoc \
	    --python_out=$(PACKAGE) \
	    --proto_path=protobuf \
	    $(PROTO_SOURCE)

test: ${VENV_BIN_ACTIVATE} .venv/${FW_VERSION}_reMarkable2-${FW_DATA}.signed $(OBJ)
	. ${VENV_BIN_ACTIVATE}; \
	python test.py

all: release

.PHONY: \
	all \
	build \
	clean \
	dev \
	executable \
	install \
	release \
	sdist \
	wheel \
	test

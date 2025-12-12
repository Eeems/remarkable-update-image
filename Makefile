.DEFAULT_GOAL := all
VERSION := $(shell grep -m 1 version pyproject.toml | tr -s ' ' | tr -d "'\":" | cut -d' ' -f3)
PACKAGE := $(shell grep -m 1 name pyproject.toml | tr -s ' ' | tr -d "'\":" | cut -d' ' -f3)
RM2_FW_VERSION := 2.13.0.758
RM2_FW_DATA := 2N5B5nvpZ4-
RM1_FW_VERSION=3.11.3.3
RMPP_FW_VERSION=3.20.0.92

SHELL := /bin/bash
ifeq ($(OS),Windows_NT)
	SHELL := /bin/bash
	ifeq ($(VENV_BIN_ACTIVATE),)
		VENV_BIN_ACTIVATE := .venv/Scripts/activate
	endif
	CODEXCTL := https://github.com/Jayy001/codexctl/releases/download/1765093380/windows-latest.zip
	CODEXCTL_HASH := 5d9b2bb323a33c7f5616aee36940df7c163f43bc81c6b1ff7bcd3aa3c9c489d6
	CODEXCTL_BIN := codexctl.exe
else
	ifeq ($(VENV_BIN_ACTIVATE),)
		VENV_BIN_ACTIVATE := .venv/bin/activate
	endif
	UNAME_S := $(shell uname -s)
	ifeq ($(UNAME_S),Darwin)
		CODEXCTL := https://github.com/Jayy001/codexctl/releases/download/1765093380/macos-latest.zip
		CODEXCTL_HASH := 7e530f5f0995f9778e591ed22a314494885a7cfcfd26aa655fbabf2ae960c5de
	else
		CODEXCTL := https://github.com/Jayy001/codexctl/releases/download/1765093380/ubuntu-latest.zip
		CODEXCTL_HASH := 9cf5b27e95e7cc1a961e41e26c8b71cd38f77fad38f819fdfced2ee1f3e2ebd3
	endif
	CODEXCTL_BIN := codexctl
endif

PROTO_SOURCE := $(wildcard protobuf/*.proto)
PROTO_OBJ := $(addprefix $(PACKAGE),$(PROTO_SOURCE:%.proto=%_pb2.py))

OBJ := $(wildcard ${PACKAGE}/**)
OBJ += requirements.txt
OBJ += pyproject.toml
OBJ += README.md
OBJ += $(PROTO_OBJ)

ifeq ($(VENV_BIN_ACTIVATE),)
VENV_BIN_ACTIVATE := .venv/bin/activate
endif

ifeq ($(PYTHON),)
PYTHON := python
endif

WHEEL_NAME := $(shell python wheel_name.py)

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
	        dist/${WHEEL_NAME}; \
	else \
	    pip install \
	        --user \
	        --force-reinstall \
	        --no-index \
	        --find-links=dist \
	        ${PACKAGE}; \
	fi

sdist: dist/${PACKAGE}-${VERSION}.tar.gz

wheel: dist/${WHEEL_NAME}

dist:
	mkdir -p dist

dist/${PACKAGE}-${VERSION}.tar.gz: ${VENV_BIN_ACTIVATE} dist $(OBJ)
	. ${VENV_BIN_ACTIVATE}; \
	python -m build --sdist

dist/${WHEEL_NAME}: ${VENV_BIN_ACTIVATE} dist $(OBJ)
	. ${VENV_BIN_ACTIVATE}; \
	python -m build --wheel
	if ! [ -f "${WHEEL_NAME}" ]; then \
	  echo "${WHEEL_NAME} Missing!"; \
	  exit 1; \
	fi

${VENV_BIN_ACTIVATE}: requirements.txt
	@echo "Setting up development virtual env in .venv"
	python -m venv .venv
	. ${VENV_BIN_ACTIVATE}; \
	python -m pip install wheel build ruff protobuf-protoc-bin==27.3; \
	python -m pip install \
	    --extra-index-url=https://wheels.eeems.codes/ \
	    -r requirements.txt


.venv/codexctl.zip: ${VENV_BIN_ACTIVATE}
	curl -L "${CODEXCTL}" -o .venv/codexctl.zip
	@bash -c 'if ! sha256sum -c <(echo "${CODEXCTL_HASH} .venv/codexctl.zip"); then \
	    echo "Hash mismatch, removing invalid codexctl.zip"; \
	    rm .venv/codexctl.zip; \
	    exit 1; \
	fi'

.venv/bin/${CODEXCTL_BIN}: .venv/codexctl.zip
	unzip -n .venv/codexctl.zip -d .venv/bin
	chmod +x .venv/bin/${CODEXCTL_BIN}

.data:
	mkdir .data

IMAGES := .data/${RM2_FW_VERSION}_reMarkable2-${RM2_FW_DATA}.signed
.data/${RM2_FW_VERSION}_reMarkable2-${RM2_FW_DATA}.signed: .venv/bin/${CODEXCTL_BIN} .data
	.venv/bin/${CODEXCTL_BIN} download --hardware rm2 --out .data ${RM2_FW_VERSION}

IMAGES += .data/remarkable-production-memfault-image-${RM1_FW_VERSION}-rm1-public
.data/remarkable-production-memfault-image-${RM1_FW_VERSION}-rm1-public: .venv/bin/${CODEXCTL_BIN} .data
	.venv/bin/${CODEXCTL_BIN} download --hardware rm1 --out .data ${RM1_FW_VERSION}

IMAGES += .data/remarkable-production-memfault-image-${RMPP_FW_VERSION}-rmpp-public
.data/remarkable-production-memfault-image-${RMPP_FW_VERSION}-rmpp-public: .venv/bin/${CODEXCTL_BIN} .data
	.venv/bin/${CODEXCTL_BIN} download --hardware rmpp --out .data ${RMPP_FW_VERSION}

$(PROTO_OBJ): $(PROTO_SOURCE) ${VENV_BIN_ACTIVATE}
	. ${VENV_BIN_ACTIVATE}; \
	protoc \
	    --python_out=$(PACKAGE) \
	    --proto_path=protobuf \
	    $(PROTO_SOURCE)

test: ${VENV_BIN_ACTIVATE} $(IMAGES) $(OBJ)
	. ${VENV_BIN_ACTIVATE}; \
	python -u test.py

all: release

lint: $(VENV_BIN_ACTIVATE)
	. $(VENV_BIN_ACTIVATE); \
	python -m ruff check

lint-fix: $(VENV_BIN_ACTIVATE)
	. $(VENV_BIN_ACTIVATE); \
	python -m ruff check

format: $(VENV_BIN_ACTIVATE)
	. $(VENV_BIN_ACTIVATE); \
	python -m ruff format --diff

format-fix: $(VENV_BIN_ACTIVATE)
	. $(VENV_BIN_ACTIVATE); \
	python -m ruff format

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
	test \
	lint \
	lint-fix \
	format \
	format-fix

.DEFAULT_GOAL := all
VERSION := $(shell grep -m 1 version pyproject.toml | tr -s ' ' | tr -d "'\":" | cut -d' ' -f3)
PACKAGE := $(shell grep -m 1 name pyproject.toml | tr -s ' ' | tr -d "'\":" | cut -d' ' -f3)
RM2_FW_VERSION := 2.15.1.1189
RM2_FW_DATA := wVbHkgKisg-
RM1_FW_VERSION=3.11.3.3
RMPP_FW_VERSION=3.20.0.92

SHELL := /bin/bash
ifeq ($(OS),Windows_NT)
	SHELL := /bin/bash
	ifeq ($(VENV_BIN_ACTIVATE),)
		VENV_BIN_ACTIVATE := .venv/Scripts/activate
	endif
	CODEXCTL := https://github.com/Jayy001/codexctl/releases/download/1752948641/windows-latest.zip
	CODEXCTL_HASH := a3c2164e8ec4f04bf059dfcd1cc216e5911f24e37ce236c25a8b420421d3266a
	CODEXCTL_BIN := codexctl.exe
else
	ifeq ($(VENV_BIN_ACTIVATE),)
		VENV_BIN_ACTIVATE := .venv/bin/activate
	endif
	UNAME_S := $(shell uname -s)
	ifeq ($(UNAME_S),Darwin)
		CODEXCTL := https://github.com/Jayy001/codexctl/releases/download/1752948641/macos-latest.zip
		CODEXCTL_HASH := 34da200b09bba09c92a7b0c39ec5dfc6b0fa5d303a750da5a1c60d715d5016e4
	else
		CODEXCTL := https://github.com/Jayy001/codexctl/releases/download/1752948641/ubuntu-latest.zip
		CODEXCTL_HASH := 209d192788576eb9d631cff8d69702ccf67bc3be07573b0adfe0ea3dc32d0227
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

IMAGES := .venv/${RM2_FW_VERSION}_reMarkable2-${RM2_FW_DATA}.signed
.venv/${RM2_FW_VERSION}_reMarkable2-${RM2_FW_DATA}.signed: .venv/bin/${CODEXCTL_BIN}
	.venv/bin/${CODEXCTL_BIN} download --hardware remarkable2 --out .venv ${RM2_FW_VERSION}

IMAGES += .venv/remarkable-production-memfault-image-${RM1_FW_VERSION}-remarkable1-public
.venv/remarkable-production-memfault-image-${RM1_FW_VERSION}-remarkable1-public: .venv/bin/${CODEXCTL_BIN}
	.venv/bin/${CODEXCTL_BIN} download --hardware rmpp --out .venv ${RM1_FW_VERSION}

IMAGES += .venv/remarkable-production-memfault-image-${RMPP_FW_VERSION}-rmpp-public
.venv/remarkable-production-memfault-image-${RMPP_FW_VERSION}-rmpp-public: .venv/bin/${CODEXCTL_BIN}
	.venv/bin/${CODEXCTL_BIN} download --hardware rmpp --out .venv ${RMPP_FW_VERSION}

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

#!/bin/bash

# binutils build
set -e
set -x


cd wishbone-tool
cargo build --release

install -d $PREFIX/bin
install target/release/wishbone-tool $PREFIX/bin

@echo on

cd wishbone-tool
cargo build --release

copy target\release\wishbone-tool.exe %PREFIX%\Library\bin\wishbone-tool.exe

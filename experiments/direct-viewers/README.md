# Direct viewers: initial feasibility experiment

The DOS 3.3 prototype has been integrated into the production readers.
See [DOS-VIEWERS.md](../../docs/DOS-VIEWERS.md) for commands, supported
formats, memory measurements and remaining work.

Production sources are `src/plugins/dosview.c`,
`src/plugins/dos_stream.h`, `src/plugins/dosview.s` and `src/fs_keys.s`. The experiment C/header
and regression entry points forward to these sources, so there is no
second implementation to keep in sync.

`build.py` still explicitly builds and checks the production reader on
both CPUs; normal builds now include DOSVIEW automatically. The old
`bench.py` exercises the explicit ! menu choice. `bench/dosview.py`
exercises the integrated T/H/I and Return commands and the write/execute
guard on a disposable Disk II source and DOS image.

The source is always read-only, no extraction or temporary is needed,
and AUX storage is untouched. The native driver path has been tested
under POM2; physical Apple II/drive qualification remains pending.
WOZ and Pinball remain excluded.

<!-- vim: set tw=80: -->
# About kernel-sandbox
*Looking for CLI commands, troubleshooting, or how to run the pipeline? See the [Execution Guide](README-execute.md).*

## What it is

A CLI that takes a kernel-source commit and gets you a **booted QEMU VM running
that kernel**

One command replaces: checkout -> patch -> configure -> compile -> package ->
provision a VM disk -> boot -> SSH in.

## Why it exists

`--mode fast` is there to quickly build in a right tool-chain container and boot
the commit.

`--mode rpm` is there to build kernel rpms, inject them into a VM image, boot.

## The pipeline, in one picture

```
 kernel-sandbox CLI
        |
        v
 +----------------+     +--------------+     +----------------+     +-------------+
 |  git worktree   | --> | BuildEngine  | --> | ImagePreparer  | --> | BootEngine  |
 |  (per commit)   |     +--------------+     +----------------+     +-------------+
 +----------------+       fast: containerized    fast: dracut/         spawns QEMU,
        |                 `make`, cached by       busybox initrd        mounts workspace
        |                 commit+arch+config      rpm: install RPMs     (9p) or qcow2 disk,
        |                 rpm: host `osc build`,   into qcow2 via        auto-SSH if requested
        |                 harvests matching RPMs    virt-customize
        |                 into the same cache
        |
        v
 tmp/.kernel-sandbox-cache/
   build_artifacts/<commit>/<arch>/<flavor>/
   base-images/  (rpm-mode qcow2s)
        ^
        |
   `list-cache` reads this to show what's
   already built and ready to boot again
```

Each stage is isolated and re-runnable on its own (`build` / `image` / `boot`) -
`boot` alone reads straight from the cache above, no recompilation.

## Two modes, one pipeline

| Aspect | `--mode fast` (default) | `--mode rpm` |
|---|---|---|
| Compiles (`BuildEngine`) | `make` in a container | Full SUSE RPM build via host `osc build` |
| Prepares (`ImagePreparer`) | dracut/busybox initrd | Installs built RPMs into a qcow2 via `virt-customize` |
| Boots (`BootEngine`) | Kernel + initrd directly | Full QCOW2 disk (with kernel rpms installed) |

Both converge on the same `BootEngine` and the same cache layout - the mode only
changes what `BuildEngine`/`ImagePreparer` produce.

## Module map

- `kernel-sandbox` - CLI entrypoint: arg parsing, workspace lifecycle, wiring.
- `pipeline_engines.py` - `BuildEngine` / `ImagePreparer` / `BootEngine`, the
  three pipeline stages above.
- `libs/kernel_source_git.py` - git worktree-per-commit management (pygit2).
- `libs/config_manager.py` - per-arch/per-branch config from
  `kernel_sandbox_profiles.yaml` + `rpm/config.sh`.
- `libs/container_engine.py`, `libs/virtual_engine.py` - podman and QEMU process
  wrappers respectively.
- `libs/initrd_builder.py`, `libs/image_customizer.py` - initrd and QCOW2
  content generation (see note below).
- `libs/cache_metadata.py` - what `list-cache` reads.
- `libs/errors.py` - `KernelSandboxError` base exception.

## Where this is headed
Based on feedback from the SUSE developer community, we are tracking several
architectural evolutions for this tool. Treat the internal mechanics of
`kernel-sandbox` as volatile while we streamline the pipeline:

* **Virtualization and Initrd overhaul:** The current `libs/initrd_builder.py` and
  QEMU orchestration layers are functional but maintain a large footprint. We
  are actively evaluating both `rapido-linux/rapido` and `virtme-ng` (`vng`) as
  potential replacements for the initrd generation and boot flow. If the
  development community prefers one of these ecosystems, `kernel-sandbox` will
  pivot to wrap them.
* **Centralized architecture mapping:** Currently, `kernel_sandbox_profiles.yaml`
  serves as a locally scoped configuration file to map architectures,
  cross-compilers, and QEMU profiles. The ideal end-state for the kernel-source
  repository is a globally centralized `arch-config` API. Refactoring the global
  architecture mapping across all legacy scripts is out of scope for this
  initial enablement, but once a unified API is designed and merged,
  `kernel-sandbox` will be updated to consume it and drop its local YAML
  entries.

## Acknowledgments

Special thanks to:
* Goldwyn Rodrigues (for the core sandbox concepts)
* David Disseldorp
* Michal Koutný
* Michal Suchánek

for their core ideas, architectural feedback, and reviews during the initial
design and enablement of this tool

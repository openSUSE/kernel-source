<!-- vim: set tw=80: -->
# How to run and troubleshoot kernel-sandbox

This guide explains how to run and work with `kernel-sandbox`. For a
higher-level explanation of what it does and why, see
`README-about.kernel-sandbox`.

By default, the sandbox runs in **fast mode** using a **dracut-generated
initrd** (direct `bzImage` boot, no full RPM build, SSH available out of the
box).

> **Heads up - the initrd and boot layers are evolving.**
> `libs/initrd_builder.py` and its `--use-busybox-initrd`/dracut machinery are
> expected to be obsoleted/rewritten in the future. We are evaluating
> `rapido-linux/rapido` and `virtme-ng` to handle the VM orchestration and
> initrd generation. If you fixing/extending the initrd internals, keep changes
> minimal - this layer is on its are fixing or extending the initrd internals
> today, keep your changes minimal—this layer is on its way out.

## A note for developers and reviewers of this automation

- **The booted initrd/qcow2 is intentionally not a hardened image.**
  Passwordless root, permissive SSH config, no firewall - by design. The entire
  point of this tool is a fast, disposable, local test sandbox, not a
  security-reviewed artifact or anything that ships. Please evaluate it against
  that goal rather than production-image hardening standards.
- **If you only want the compiled kernel/RPM and not a booted sandbox**, request
  the `build` phase explicitly (`... build`) instead of running the full
  pipeline or `boot` - no VM is spawned at all in that case.
- **Changes to the scripts/libs/assets** should go through the internal
  kernel-source development workflow (kerncvs / user-mode push).
- **If you are an architecture owner and spot an issue** in
  `kernel_sandbox_profiles.yaml`'s arch profiles or mappings, please raise a
  corrective PR through the same internal development workflow.

---

## Prerequisites

Before running the pipeline, ensure you have the required dependencies installed
on your host system:

```bash
zypper in python313-PyYAML # The '313' suffix will vary depending on your developer environment
zypper in python313-pygit2 # The '313' suffix will vary depending on your developer environment
zypper in ca-certificates-suse

# You will also need the QEMU system emulator matching your target --arch
# (ex: qemu-x86 for x86_64, qemu-arm for arm64) to boot the sandbox.

# fast mode dependencies (default mode)
# Required for containerized kernel compilation, sequence patching, and initrd generation.
zypper in podman patch rapidquilt qemu-linux-user cpio

# rpm mode dependencies
# Required for native host RPM builds (via osc) and QCOW2 image manipulation.
zypper in osc libguestfs guestfs-tools qemu-img qemu-tools
```

kernel-sandbox script itself checks for the phase-specific subset of these
(`git`, `podman`, `virt-customize`, `guestfish`, `cpio`, `qemu-system-<arch>`,
`qemu-img`) before running and will tell you exactly what is missing and which
`zypper in ...` line to run.

## Preparing your environment

Before running any script, make sure you configure your host workspace pointers.
You can define these variables directly in your terminal:

* `LINUX_GIT`: (ex: `/srv/git/linux.git/`). Needed in environments where
  `LINUX_TAR_DIR` or `/mounts/mirror` is not visible, so the `sequence-patch`
  tool can create linux tarballs.
* `SCRATCH_AREA`: (optional) point this at faster storage (ex: `/dev/shm`) if
  you want to compile there. When set, `<cache_dir>` (see Glossary below) moves
  there instead of living under the repo you ran kernel-sandbox from.

## Glossary

- **`<cache_dir>`**: kernel-sandbox's cache root, used throughout this doc.
  Resolves to `$SCRATCH_AREA/.kernel-sandbox-cache` if `SCRATCH_AREA` is set,
  otherwise `./tmp/.kernel-sandbox-cache` relative to wherever you ran
  kernel-sandbox from. Contains:
  - `<cache_dir>/workspaces/<commit_hash>/` - the per-commit git worktree (see
    "Uncommitted changes are not picked up" below).
  - `<cache_dir>/build_artifacts/<commit>/<arch>/<flavor>/` - cached
    kernel/RPM/initrd build output, keyed by commit+arch+config (see
    `list-cache` and "Cache management and clearing").
  - `<cache_dir>/base-images/` - downloaded JeOS images and rpm-mode qcow2s.

### Uncommitted changes are not picked up

kernel-sandbox never looks at the staged/unstaged/untracked state of the repo
you ran it from. `--commit`/`--tag` (or `HEAD` if you pass neither) is resolved
to a commit hash and checked out into its own dedicated git worktree - your
working tree's unstaged or untracked changes are not part of that commit, so
they are absent from the build.

**If you want to test local changes, commit them first** (even to a throwaway
local commit/branch) before pointing kernel-sandbox at that ref.

## Architecture support matrix

| Arch | Status |
|---|---|
| `x86_64` | Supported - build and boot both work today. |
| `arm64` | Supported - build and boot both work today. |
| `s390x` | Supported - build and boot both work today. |
| `ppc64le` | Supported - build and boot both work today. |
| `i386`, `i586`, `armv7hl`, `armv6hl`, `ppc64`, `s390`, `riscv64`, `ia64` | Not yet evaluated - profiles exist but end-to-end build/boot has not been tried. |

## Discovering which architectures and config flavors you can test

`--arch` is currently limited to `x86_64` and `arm64` (defaults to your host
arch).

`--config` accepts whatever flavor directories actually exist in the kernel
source tree you are testing - list them directly from a checkout:

```bash
ls config/x86_64/     # -> default, rt, azure, kvmsmall, ...
ls config/arm64/
```

Any directory name under `config/<arch>/` in the branch/commit you are testing
is a valid `--config` value for that arch. Not every branch has every flavor -
if `--config` doesn't exist for the arch/branch you picked, the build phase
fails fast with a clear "Kernel configuration missing" error naming the exact
path it looked for.

---

## Full CLI reference

```
./scripts/kernel-sandbox/kernel-sandbox [options] [build|image|boot|list-cache]
```

| Flag | Description |
|---|---|
| `--tag TAG` / `--commit HASH` | Git ref to build (mutually exclusive). Defaults to `HEAD` if neither is given. |
| `--arch {x86_64,arm64}` | Target architecture (default: host arch). |
| `--config FLAVOR` | Config flavor under `config/<arch>/` (default: `default`). |
| `--mode {fast,rpm}` | `fast` = direct bzImage boot (default). `rpm` = full RPM build + QCOW2 injection. |
| `--use-busybox-initrd` | Fast mode only: swap the default dracut initrd for a minimal busybox one. **No SSH in this mode** - console only. |
| `--extra-qemu "..."` | Raw extra arguments appended to the QEMU invocation. |
| `--refresh-cache` | Ignore cached kernel/RPM/initrd artifacts and rebuild from scratch. |
| `--ssh` | Auto-connect via SSH right after boot (this is the default behavior already in `--mode rpm`). |
| `--qcow2 PATH` | Use this local `.qcow2` as the RPM-mode base image instead of resolving one from IBS/OBS. |
| `--rpm-build-root PATH` | Build root passed to `osc build --root=` in `--mode rpm` (default: `/var/tmp/build-root`). |
| `--clean-workspace` | Delete the git worktree for this commit when the run finishes. |
| `build` / `image` / `boot` | Optional positional: run only that phase instead of the full pipeline. |
| `list-cache` | Print every cached build and the exact command to boot it, then exit. |

---

## Common sandbox invocations

### Fast mode (direct bzImage boot with workspace mount)
This is the default mode. It compiles the kernel in a container, packs a dracut
initrd, and boots QEMU in a few minutes.

> **CPU usage note.** `sequence-patch --rapid` (rapidquilt) threads across every
> online CPU, and the containerized `make` step also builds with `-j$(nproc
> --all)` - both intentionally use 100% of every core. On a higher-end lab/build
> machine this is barely noticeable, but on a developer laptop expect occasional
> screen freezing/UI slowness during these two windows - it is expected.

```bash
# Compile and boot a specific commit for the "default|rt|azure|kvmsmall" flavor
LINUX_GIT=/srv/git/linux.git/ ./scripts/kernel-sandbox/kernel-sandbox --commit "origin/SL-16.0" --config <default|rt|azure|kvmsmall>

# Same, but against a tag instead of a commit
LINUX_GIT=/srv/git/linux.git/ ./scripts/kernel-sandbox/kernel-sandbox --tag rpm-6.12.0-160000.37 --config <default|rt|azure|kvmsmall>
```

### Fast mode with a lightweight busybox initrd
Skips dracut entirely for the quickest possible boot.

```bash
LINUX_GIT=/srv/git/linux.git/ ./scripts/kernel-sandbox/kernel-sandbox --commit "origin/SL-16.0" --use-busybox-initrd
```

**No SSH server here** - there is no sshd in this initrd, so `ssh -p 2222 ...`
will not work and `--ssh` has nothing to connect to. You get the QEMU serial
console only. That said:
- **Networking is up** (DHCP via `udhcpc`), so anything that talks over the
  9p-mounted workspace or reaches out to the network still works.
- **RPM installation still works** - `rpm -i some_pkg.rpm` unpacks RPMs fine
  even without a package manager, if you brought testing utilities as standalone
  `.rpm` files.
- **Busybox applets only** - no `zypper`, no `gcc`; only whatever busybox itself
  provides. This is the minimal, fastest-boot environment, not a general-purpose
  one - use the default dracut fast mode above if you need SSH or a fuller
  userspace (with zypper and other basic utils).

### RPM mode (full package creation and injection)
Compiles full SLES RPMs from specs, takes a SLES base image (JeOS), injects the
fresh kernel RPMs, regenerates GRUB, and launches a full virtual machine.

```bash
LINUX_GIT=/srv/git/linux.git/ ./scripts/kernel-sandbox/kernel-sandbox --mode rpm --commit "origin/SL-16.0" --config default

# with an explicit local base image instead of an IBS/OBS download
LINUX_GIT=/srv/git/linux.git/ ./scripts/kernel-sandbox/kernel-sandbox --mode rpm --commit "origin/SL-16.0" \
    --qcow2 /mounts/dist/ibs/SUSE/Products/SLE-Product-Minimal/16.1/x86_64/SLES-16.1-Minimal-VM.x86_64-kvm-and-xen-010-OpenBeta.qcow2
```

### Isolated phase runs

```bash
# Build only - compile the kernel/RPMs, don't touch QEMU
LINUX_GIT=/srv/git/linux.git/ ./scripts/kernel-sandbox/kernel-sandbox --commit "origin/SL-16.0" --config default build

# Image only - prepare the initrd/qcow2 from already-built artifacts
./scripts/kernel-sandbox/kernel-sandbox --commit "origin/SL-16.0" --config default image

# Boot only - reboot an already-built VM without recompiling anything
./scripts/kernel-sandbox/kernel-sandbox --commit "origin/SL-16.0" --config default boot
```

### Listing what is already cached
Forgot which commit/arch/config/mode combination you built earlier? `list-cache`
scans `<cache_dir>` and prints each cached build plus the exact command to boot
it straight from cache (skipping build+image phases):

```bash
./scripts/kernel-sandbox/kernel-sandbox list-cache
```

```
[0] f8bc143  x86_64  kvmsmall  rpm   ready   2h ago
    ./scripts/kernel-sandbox/kernel-sandbox --commit f8bc143 --arch x86_64 --config kvmsmall --mode rpm boot
[1] 4003d3e  x86_64  default   fast  ready   1d ago
    ./scripts/kernel-sandbox/kernel-sandbox --commit 4003d3e --arch x86_64 --config default --mode fast boot
```

Just copy the printed line for the entry you want and run it - `boot`-phase
isolation means it goes straight to QEMU, no rebuild.

---

## Connecting to a running sandbox via SSH / SFTP

SSH is available by default in **fast mode** (dracut initrd) and **rpm mode**.
It is **not** available with `--use-busybox-initrd` (console-only, no sshd).
Root login is passwordless in both cases - this is a local testing sandbox, not
a hardened image.

QEMU forwards host port `2222` to the guest's port `22`
(`hostfwd=tcp::2222-:22`), so from the **same host** running kernel-sandbox:

```bash
# SSH in
ssh -p 2222 root@localhost

# Copy a file into the sandbox
scp -P 2222 ./my_test_core root@localhost:/root/
# NOTE: if the above `scp` does not work, then try with `scp -O -P 2222`, legacy SCP proto instead of SFTP

# Interactive SFTP session
sftp -P 2222 root@localhost
```

If you pass `--ssh` (or you are in `--mode rpm`, where it is on by default),
kernel-sandbox auto-connects for you right after boot - you don't need to run
the `ssh` command above yourself in that case.

### From another node on the network

Because the forward isn't bound to a specific address, port 2222 on the **host
machine's own IP** (not `localhost`) is reachable from other nodes on the same
network, subject to your host's firewall:

```bash
ssh -p 2222 root@<host-machine-ip-or-hostname>
scp -P 2222 ./what-you-want-copy root@<host-machine-ip-or-hostname>:/root/
sftp -P 2222 root@<host-machine-ip-or-hostname>
```

If this doesn't work, check that nothing is blocking TCP/2222 inbound on the
host (firewalld/iptables), and that the VM is actually still running
(`list-cache`'s `ready` status only reflects on-disk artifacts, not whether a
QEMU process is currently up).

---

## Inside the fast mode environment

kernel-sandbox does **not** mount the repository you ran it from. For every
`--commit`/`--tag` it builds, it creates a dedicated **git worktree** under
`<cache_dir>/workspaces/<commit_hash>/` (reused on later runs against the same
commit), checked out at exactly that commit. It is *this* worktree - not your
CWD checkout - that gets mounted inside the VM at `/mnt/workspace` via **9p
virtio passthrough**.

Any change you make from inside the VM under `/mnt/workspace` lands directly in
that worktree directory on the host (and vice versa) - it is the same directory,
not a copy. It is a separate checkout from whatever branch you have checked out
in your own working copy, so edits there do not touch your main checkout unless
you go looking at that worktree path directly.

When the system boots, you will see an initialization log similar to this:

```text
[    2.604318][    T1] Run /custom_init as init process
====================================================
    kbox - Fast Boot Dracut+Native Sandbox Initialization
====================================================
Mounting API filesystems... [ OK ]
Loading kernel modules manually... [ OK ]
Initializing loopback and network interfaces...
Requesting DHCP lease for eth0... [    1.307498]
[    1.309327] NET: Registered protocol family 17
[ OK ]
Mounting 9p Host Passthrough... [ OK ]
Setting up SSH Server in background... [ STARTED ASYNC ]

Sandbox environment (DRACUT mode) active. Dropping to a root shell.
Current directory: /mnt/workspace
====================================================
 [ENVIRONMENT NOTICE]:
  * This is a DRACUT-BASED testing sandbox.
  * Native package utilities (zypper, rpm, vim) ARE present.
  * Network is Functional with internet access.
  * SSH is Active. Connect via: ssh -p 2222 root@localhost
  * WORKSPACE MAPPING:
    The /mnt/workspace directory is bound to the isolated host worktree:
    <cache_dir>/workspaces/192937996fa5358115e12b1930db378f08054152
    (Modifications here will be reflected on your host's WORKSPACE MAPPING)
    (Modifications here will NOT affect your host's active CWD)
  * For full fledged VM sandbox environment, terminate
    execution and relaunch the sandbox script with: kernel-sandbox --mode rpm
====================================================

kernel-sandbox:/mnt/workspace# ls
COPYING           config           patches.rpmify   series.conf
README.BRANCH     config.conf      patches.suse     supported.conf
README.blacklist  doc              rpm              sysctl
README.md         kabi             run-tests        tmp
blacklist.conf    patches.kabi     scripts
```

### What can you do in this environment?

1. **Run tests**: navigate to `/mnt/workspace/run-tests`(if you already placed
   it in your host's WORKSPACE MAPPING) and launch scripts directly from the
   mounted worktree.
2. **SSH/SFTP in** from the host (or another node) as shown above, instead of
   using the QEMU console - much more convenient for copying files or running
   longer test sessions.
3. **Active host mirroring**: any edits under `/mnt/workspace` from inside the
   VM immediately reflect on the host's worktree directory, and vice versa.
4. **Fuller userspace by default**: this default dracut-based fast mode carries
   git, gcc, make, vim, zypper, rpm, strace, and more - see
   `assets/dracut_cmd.tmpl` for the exact tool list baked in.
   `--use-busybox-initrd` trades all of that (and SSH) away for the fastest
   possible boot - see "Fast mode with a lightweight busybox initrd" above for
   what is still available there.

---

## Cache management and clearing

kernel-sandbox keys its cache by commit hash + arch + config flavor under
`build_artifacts/<commit>/<arch>/<flavor>/` to avoid recompiling a kernel you
have already built (see `list-cache` above to inspect what is there).

### How to ignore the cache
To force a clean, from-scratch build for one run without deleting anything (use
the flag `--refresh-cache`):

```bash
LINUX_GIT=/srv/git/linux.git/ ./scripts/kernel-sandbox/kernel-sandbox --commit "origin/SL-16.0" --refresh-cache
```

### Rebuilding just the initrd (dracut/init script changes)
If you are iterating on `libs/initrd_builder.py`, `assets/dracut_cmd.tmpl`, or
`assets/initrd_init*.tmpl` and don't need to recompile the kernel itself, delete
only the cached `initrd_custom.gz` for that commit/arch/config, then rerun just
the `image` phase - `build` stays a cache hit, so it is much faster than a full
`--refresh-cache` run:

```bash
rm -f <cache_dir>/build_artifacts/<commit>/<arch>/<flavor>/initrd_custom.gz
./scripts/kernel-sandbox/kernel-sandbox --commit <commit> --arch <arch> --config <flavor> --mode fast image
```

`image` reports a cache hit on the kernel but recompiles the initrd from scratch
since its cached file is gone. Follow up with `boot` (or just rerun the full
command with no phase argument) to boot with the freshly rebuilt initrd.

### How to completely clear the cache directory manually
```bash
sudo rm -rf <cache_dir>/
```
(see the Glossary above for what `<cache_dir>` resolves to on your setup)

---

## Disk space considerations

The two modes have very different disk profiles inside the guest - be aware of
which one applies before you start copying large test artifacts around.

**`--mode rpm`**: the whole guest filesystem lives on the qcow2 disk, so
available space is whatever the base JeOS image ships with (commonly ~20G free):

```
localhost:~ # df -h
Filesystem      Size  Used Avail Use% Mounted on
/dev/vda3        24G  3.5G   20G  15% /
...
```

**`--mode fast`**: `/mnt/workspace` (the 9p-mounted worktree) inherits whatever
free space your host filesystem has - typically much larger - but everything
else (`/tmp`, `/dev/shm`, `/run`) is `tmpfs`, bounded by the VM's RAM allocation
(4G/8G mem allocation, so 50% of RAM is the disk space inside), not by host
disk:

```
kernel-sandbox:/mnt/workspace# df -h
Filesystem      Size  Used Avail Use% Mounted on
tmpfs           3.9G     0  3.9G   0% /tmp
host_mount      893G   67G  822G   8% /mnt/workspace
...
```

**Practical implication**: write large build outputs or test artifacts under
`/mnt/workspace` in fast mode, not on VM's tmpfs volumes, these volumes will
fill up and start failing well before `/mnt/workspace` does.

There is currently no dedicated flag to resize the QEMU VM (launched in fast|rpm
mode), attach extra volumes, or bump VM RAM/CPU count. You *can* work around
this today by appending raw QEMU flags via `--extra-qemu` (it is appended last,
so it wins over kernel-sandbox's own `-m`/`-smp` for most single-value options)
- for example `--extra-qemu "-m 16384 -smp 8"` or `--extra-qemu "-drive
file=/path/to/extra.img,if=virtio"` for an additional volume. A dedicated flag
for this is tracked as a future enablement item below.

```bash
LINUX_GIT=/srv/git/linux.git/ ./scripts/kernel-sandbox/kernel-sandbox --commit 1929379 --arch arm64 --config default --mode fast boot \
--extra-qemu "-m 33536 -smp 16"
```
---

## Running the test suite

After developing or making any change to `scripts/kernel-sandbox` (libs, assets,
scripts), run the unit test suite from the `scripts/kernel-sandbox` directory to
confirm no regressions were introduced:

```bash
# under scripts/kernel-sandbox directory
python3 -m unittest discover -v -s tests
```

This runs every `tests/test_*.py` file. Fix any failures (or update the affected
test if the behavior change was intentional) before sending your changes through
review.

---

## Future development / enablement

Not implemented yet - listed here so it is clear what is intentionally out of
scope today versus what is just missing:

- **`ccache` support** for faster repeat compiles across commits/flavors.
- **`ppc64le` and `s390x` enablement** - wiring the existing
  `kernel_sandbox_profiles.yaml` profiles into `--arch` and validating
  build+boot end to end (see the architecture support matrix above).
- **Replacing the initrd/boot layer with `rapido-linux/rapido`** - see the
  callout at the top of this document.
- **`riscv` container build enablement** for Tumbleweed-based builds.
- **A real flag for extra CPU/memory/volumes** (maybe), instead of the
  `--extra-qemu` workaround described in "Disk space considerations" above.

---

## Troubleshooting and limitations

### The "RPM mode" hang
* When booting with `--mode rpm`, the QEMU window/terminal output redirects to
  the guest's initial configuration stages.
* kernel-sandbox automates these steps via `virt-customize` (bypassing setup
  screens, enabling automatic/passwordless root login).
* This automation is tested against SL-16.x, SLE15-SP5/6/7, and 12-SP5 with
  `default` config only - other branches or flavors may hang waiting on a guest
  setup screen that was never automated for that image.
* If it hangs, you can always manually launch the VM with the exact `qemu`
  invocation kernel-sandbox printed to the console before spawning it.
* If the pipeline aborts before QEMU even launches with an SSL or "Base image
  find failed" error, your host may not have the SUSE CA certificates loaded to
  download the JeOS image from updates.suse.de. You can bypass this by manually
  downloading the QCOW2 image and providing it via the --qcow2 flag.

### "Missing qemu-system-..." binary error on host
```bash
sudo zypper in qemu-x86 qemu-arm qemu-tools
```

### Missing `virt-customize` / `guestfish` error
```bash
sudo zypper in guestfs-tools libguestfs
```

### "Target project (IBS|OBS) not specified" in `--mode rpm`
Your `rpm/config.sh` (in the branch/commit you are testing) needs at least one
of `IBS_PROJECT` or `OBS_PROJECT` set. kernel-sandbox prefers IBS when it is
both reachable (are you on the SUSE internal network/VPN?) and configured -
otherwise it falls back to OBS.

### Invalid `--commit`/`--tag`
An unresolvable git reference fails with `[ERROR] Could not resolve requested
git reference: ...`
- double check the ref exists in the kernel-source repo.

### Reproducing `--mode rpm`'s image-customization step by hand
If `libs/image_customizer.py`'s `install_rpms_to_image()` (the `virt-customize`
step that installs your built RPMs into the base qcow2) fails and the wrapped
error isn't enough to diagnose, here is the same sequence run manually, one step
at a time, against a throwaway qcow2:

```bash
####
# RPMBUILD for flavors(default|rt|azure) - MANUAL instructions
####

mkdir -p tmp/.kernel-sandbox-cache/base-images
cd tmp/.kernel-sandbox-cache/base-images

# some older SLE releases have .raw.xz files
curl -L -o base-leap-15.6.qcow2 \
    https://download.opensuse.org/repositories/SUSE:/Templates:/Images:/SLES-16.0/images/SLES-16.0-Minimal-VM.x86_64-kvm-and-xen-Build41.35.qcow2

qemu-img create -f qcow2 -F qcow2 -b base-leap-15.6.qcow2 sandbox.qcow2

cd /tmp/kernel-source

# Build the RPMs using your existing container/osc flow
./scripts/tar-up -d kernel-source
./scripts/osc_wrapper build --clean kernel-source/kernel-flavor.spec

# once the rpms are built, cache them to kbox-cache
mkdir -p built-rpms
cp /var/tmp/build-root/standard-x86_64/home/abuild/rpmbuild/RPMS/x86_64/kernel-flavor-*.rpm built-rpms/

# disable jeos-firstboot
virt-customize -a sandbox.qcow2 \
--root-password password:suse \
--timezone "UTC" \
--run-command 'systemctl disable jeos-firstboot.service || true' \
--run-command 'systemctl disable jeos-firstboot-snapshot.service || true'

# upload the RPM into qcow2
virt-customize -a sandbox.qcow2 --upload \
    "/var/tmp/build-root/standard-x86_64/home/abuild/rpmbuild/RPMS/x86_64/kernel-flavor-6.12.0-0.g4184b4a.x86_64.rpm":/root/new-kernel.rpm

# install the RPM inside qcow2
virt-customize -a sandbox.qcow2 --run-command 'rpm -ivh --force --oldpackage /root/new-kernel.rpm'

# identify kver
rpm -q --qf "%{VERSION}-%{RELEASE}.%{ARCH}\n" \
    -p /var/tmp/build-root/standard-x86_64/home/abuild/rpmbuild/RPMS/x86_64/kernel-flavor-6.12.0-0.g4184b4a.x86_64.rpm
6.12.0-0.g4184b4a.x86_64

# use that kver
virt-customize -a sandbox.qcow2 \
--run-command 'rpm -ivh --force --oldpackage /root/new-kernel.rpm' \
--run-command 'dracut --force --no-hostonly --kver 6.12.0-0.g4184b4a-<flavor>' \
--run-command 'grub2-mkconfig -o /boot/grub2/grub.cfg' \
--run-command "echo 'GRUB_DISABLE_SUBMENU=y' >> /etc/default/grub" \
--run-command "sed -i 's/^GRUB_DISTRIBUTOR=.*/GRUB_DISTRIBUTOR=\"kernel-sandbox-image\"/g' /etc/default/grub" \
--run-command "echo 'GRUB_DEFAULT=\"kernel-sandbox-image, with Linux 6.12.0-0.g4184b4a-<flavor>\"' >> /etc/default/grub" \
--run-command "grub2-mkconfig -o /boot/grub2/grub.cfg" \
--run-command "systemctl disable jeos-firstboot.service || true" \
--run-command "systemctl disable jeos-firstboot-snapshot.service || true" \
--run-command "mkdir -p /etc/systemd/system/serial-getty@ttyS0.service.d" \
--run-command \
"printf '[Service]\nExecStart=\nExecStart=-/sbin/agetty --autologin root --noclear %%I \$TERM\n' \
    > /etc/systemd/system/serial-getty@ttyS0.service.d/autologin.conf"

# Boot the sandbox natively
qemu-system-x86_64 \
-enable-kvm \
-cpu host \
-m 4096 \
-smp 4 \
-nographic \
-no-reboot \
-drive file=sandbox.qcow2,format=qcow2,if=virtio \
-netdev user,id=net0,hostfwd=tcp::2222-:22 \
-device virtio-net-pci,netdev=net0
```

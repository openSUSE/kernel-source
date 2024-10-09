ifndef VULNS_GIT
$(error Please set VULNS_GIT to a clone of https://git.kernel.org/pub/scm/linux/security/vulns.git)
endif
ifndef KSOURCE_GIT
$(error Please set KSOURCE_GIT to a clone of kernel-source)
endif
SHELL=/bin/bash
git_packed_refs:=$(shell git -C "$(KSOURCE_GIT)" rev-parse --path-format=absolute --git-path "packed-refs")
mk_dir := $(dir $(abspath $(lastword $(MAKEFILE_LIST))))

# URL of upstream vulns
VULNS_GIT_URL=https://git.kernel.org/pub/scm/linux/security/vulns.git

# URL of CVE
CVE2BUG_URL=https://gitlab.suse.de/security/cve-database/-/raw/master/data/cve2bugzilla

# cached data expiration in days
EXPIRE=3

ADD_REF=$(mk_dir)/add-missing-reference

WORKTREE=$(CURDIR)/git-worktree

# oldest stable 4.19 when kernel.org CNA started is from 2018
FIRST_YEAR=2018
# Outer parameter, can be overriden
YEAR=$(shell date +%Y)
# Outer parameter, can be overriden
ifndef BRANCH
$(error Please specify branch to annotate in BRANCH parameter)
endif
branch=$(subst /,_,$(BRANCH))
user=$(if $(KBUILD_USER),$(KBUILD_USER),$(USER))
branch_user=users/$(user)/$(BRANCH)/cve-refs
branch_base=$(if $(BASE_BRANCH),$(BASE_BRANCH),origin/$(BRANCH))

.PHONY: check_cache update_refs_history update_refs_$(branch)_$(YEAR)

CACHESTAMP=cachestamp

check_cache:
	@test -n "$$(find "$(CACHESTAMP)" -mtime -$(EXPIRE) -print 2>/dev/null)" || touch "$(CACHESTAMP)"

$(CACHESTAMP): check_cache

cve2bugzilla: $(CACHESTAMP)
	curl "$(CVE2BUG_URL)" -o "$@"

hash_cve_$(YEAR).dat: $(wildcard $(VULNS_GIT)/cve/published/$(YEAR)/*.sha1) $(VULNS_GIT)/.git/refs/heads/master
	@for f in $(notdir $^) ; do \
		[[ $$f == *.sha1 ]] && \
			echo $$(head -n1 $(VULNS_GIT)/cve/published/$(YEAR)/$$f) $${f%.sha1} ; \
	done | sort -k1 >"$@"

$(wildcard $(VULNS_GIT)/cve/published/$(YEAR)/*.sha1): $(VULNS_GIT)/.git/refs/heads/master

$(VULNS_GIT)/.git/refs/heads/master: $(CACHESTAMP)
	test -d $(VULNS_GIT) || git clone "$(VULNS_GIT_URL)" "$(VULNS_GIT)"
	git -C "$(VULNS_GIT)" pull
	touch "$@"

# cve2bugzilla contains multiple bugs for single CVE, use the heuristics of
# lowest numerical bug being the primary bug
cve_bug_$(YEAR).dat: cve2bugzilla
	@sed -n '/^CVE-$(YEAR)-.*BUGZILLA:/{s/^\(CVE-[^,]*\),.*BUGZILLA:\([0-9]*\).*$$/\1 \2/;p}' <"$<" | \
	sort -n -k 2 | sort -k 1b,1 -s | uniq | \
	awk '{ primary_bug=$$1 != cve; cve=$$1; print $$0, primary_bug; }' >"$@"

hash_file_$(branch).dat: $(git_packed_refs)
	@git -C "$(KSOURCE_GIT)" \
		grep -i "^git-commit[[:space:]]*:[[:space:]]*[0-9a-f]*[[:space:]]*$$" $(branch_base) -- "$(KSOURCE_GIT)/patches.suse" |\
		awk -vFS=":" '{gsub(" ", "", $$4); print $$4, $$2}' | sort -k1 >"$@"

hash_cve_bug_$(YEAR).dat: hash_cve_$(YEAR).dat cve_bug_$(YEAR).dat
	@sort -k 2b,2 hash_cve_$(YEAR).dat | \
	join -1 2 -2 1 -o 1.1,1.2,2.2,2.3 - cve_bug_$(YEAR).dat | \
	sort -k 1 >"$@"

update_refs: update_refs_$(branch)_$(YEAR)

update_refs_history:
	@git -C "$(KSOURCE_GIT)" worktree add -f -B $(branch_user) "$(WORKTREE)" $(branch_base) 2>/dev/null || \
		git -C "$(WORKTREE)" checkout -f -B $(branch_user) $(branch_base) 2>/dev/null || \
		( echo "git worktree failed, run 'make clean' in old workdir? $$(git -C "$(KSOURCE_GIT)" worktree list | grep git-worktree)" && false )
	@cd "$(WORKTREE)" >/dev/null ; \
	scripts/install-git-hooks >/dev/null || echo "WARNING: git-hooks not installed"
	set -e ; for y in $$(seq $(FIRST_YEAR) $(YEAR)) ; do \
		make --no-print-directory -f $(mk_dir)/Makefile BRANCH=$(BRANCH) YEAR=$$y update_refs ; \
	done
	@echo -e "\nResults in $(branch_user)"

update_refs_$(branch)_$(YEAR): hash_file_$(branch).dat hash_cve_bug_$(YEAR).dat
	@echo -e "\n[ $(YEAR) ] processing..."
	@set -e ; \
	join hash_file_$(branch).dat hash_cve_bug_$(YEAR).dat | \
	while read sha file cve bug primary; do \
		[ "$$primary" -eq 0 ] && continue ; \
		[ -z "$$bug" ] && echo "Unknown bug for $$cve" && continue ; \
		$(ADD_REF) -r $$cve -r "bsc#"$$bug "$(WORKTREE)/$$file" ; \
	done
	cd "$(WORKTREE)" >/dev/null ; \
	scripts/log --no-edit || true

clean:
	rm -f *_$(branch).dat
	for y in $$(seq $(FIRST_YEAR) $(YEAR)) ; do \
		rm -f *_$$y.dat ; \
	done
	-git -C "$(KSOURCE_GIT)" worktree remove -f "$(WORKTREE)"

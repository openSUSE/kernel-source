ifndef VULNS_GIT
$(error Please set VULNS_GIT to a clone of https://git.kernel.org/pub/scm/linux/security/vulns.git)
endif
ifndef KSOURCE_GIT
$(error Please set KSOURCE_GIT to a clone of kernel-source)
endif
mk_dir := $(dir $(abspath $(lastword $(MAKEFILE_LIST))))

# URL of upstream vulns
VULNS_GIT_URL=https://git.kernel.org/pub/scm/linux/security/vulns.git

# URL of CVE
CVE2BUG_URL=https://gitlab.suse.de/security/cve-database/-/raw/master/data/cve2bugzilla

# cached data expiration in days
EXPIRE=3

ADD_REF=$(mk_dir)/add-missing-reference

# oldest stable 4.19 when kernel.org CNA started is from 2018
FIRST_YEAR=2018
# Outer parameter, can be overriden
YEAR=$(shell date +%Y)
# Outer parameter, can be overriden
BRANCH=cve/linux-5.14
branch=$(subst /,_,$(BRANCH))

.PHONY: check_cache update_refs_history update_refs_$(branch)_$(YEAR)

CACHESTAMP=cachestamp

check_cache:
	@test -n "$$(find "$(CACHESTAMP)" -mtime -$(EXPIRE) -print 2>/dev/null)" || touch "$(CACHESTAMP)"

$(CACHESTAMP): check_cache

cve2bugzilla: $(CACHESTAMP)
	curl "$(CVE2BUG_URL)" >"$@"

hash_cve_$(YEAR).dat: $(wildcard $(VULNS_GIT)/cve/published/$(YEAR)/*.sha1) $(VULNS_GIT)/.git/refs/heads/master
	@for f in $^ ; do \
		[[ $$f == *.sha1 ]] && \
			echo $$(head -n1 $$f) $$(basename $${f%.sha1}) ; \
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

hash_file_$(branch).dat: $(KSOURCE_GIT)/.git/refs/remotes/origin/$(BRANCH)
	@git -C "$(KSOURCE_GIT)" \
		grep -i "^git-commit[[:space:]]*:[[:space:]]*[0-9a-f]*[[:space:]]*$$" origin/$(BRANCH) -- "$(KSOURCE_GIT)/patches.suse" |\
		awk -vFS=":" '{gsub(" ", "", $$4); print $$4, $$2}' | sort -k1 >"$@"

hash_cve_bug_$(YEAR).dat: hash_cve_$(YEAR).dat cve_bug_$(YEAR).dat
	@sort -k 2b,2 hash_cve_$(YEAR).dat | \
	join -1 2 -2 1 -o 1.1,1.2,2.2,2.3 - cve_bug_$(YEAR).dat | \
	sort -k 1 >"$@"

update_refs: update_refs_$(branch)_$(YEAR)

update_refs_history:
	set -e; pushd "$(KSOURCE_GIT)" >/dev/null ; \
	git checkout -f -B users/$$USER/$(BRANCH)/cve-refs origin/$(BRANCH) 2>/dev/null ; \
	popd >/dev/null
	for y in $$(seq $(FIRST_YEAR) $(YEAR)) ; do \
		make --no-print-directory -f $(mk_dir)/Makefile BRANCH=$(BRANCH) YEAR=$$y update_refs ; \
	done

update_refs_$(branch)_$(YEAR): hash_file_$(branch).dat hash_cve_bug_$(YEAR).dat
	@echo -e "\n[ $(YEAR) ] processing..."
	@set -e ; \
	join hash_file_$(branch).dat hash_cve_bug_$(YEAR).dat | \
	while read sha file cve bug primary; do \
		[ "$$primary" -eq 0 ] && continue ; \
		[ -z "$$bug" ] && echo "Unknown bug for $$cve" && continue ; \
		$(ADD_REF) -r $$cve -r "bsc#"$$bug "$(KSOURCE_GIT)/$$file" ; \
	done
	set -e ; pushd "$(KSOURCE_GIT)" >/dev/null ; \
	scripts/log2 --no-edit || true ; \
	popd >/dev/null

clean:
	rm -f *_$(branch).dat
	for y in $$(seq $(FIRST_YEAR) $(YEAR)) ; do \
		rm -f *_$$y.dat ; \
	done

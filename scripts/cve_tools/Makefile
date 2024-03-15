# Expects VULNS_GIT environment variable with a clone of https://git.kernel.org/pub/scm/linux/security/vulns.git
# Expects KSOURCE_GIT environment variable
CVE_TO_BUG=../cve-to-bug.py
ADD_REF=./add-missing-reference

YEAR=2024
# Outer parameter, can be overriden
BRANCH=cve/linux-5.14
branch=$(subst /,_,$(BRANCH))

hash_cve_$(YEAR).dat: $(wildcard $(VULNS_GIT)/cve/published/$(YEAR)/*.sha1)
	for f in $^ ; do \
		echo $$(head -n1 $$f) $$(basename $${f%.sha1}) ; \
	done | sort -k1 >"$@"

cve_bug_$(YEAR).dat: hash_cve_$(YEAR).dat
	for cve in $$(cut -d" " -f2 $<) ; do \
		bug=$$($(CVE_TO_BUG) $$cve) ; \
		sleep 0.3 ; \
		echo $$cve $$bug ; \
	done | sort -k 1b,1 >$@

hash_file_$(branch).dat:
	git --git-dir="$(KSOURCE_GIT)/.git" --work-tree="$(KSOURCE_GIT)" grep -i "^git-commit[[:space:]]*:[[:space:]]*" origin/$(BRANCH) -- "$(KSOURCE_GIT)/patches.suse" |\
		awk -vFS=":" '{gsub(" ", "", $$4); print $$4, $$2}' | sort -k1 >"$@"

hash_cve_bug_$(YEAR).dat: hash_cve_$(YEAR).dat cve_bug_$(YEAR).dat
	sort -k 2b,2 hash_cve_$(YEAR).dat | \
	join -1 2 -2 1 -o 1.1,1.2,2.2 - cve_bug_$(YEAR).dat | \
	sort -k 1 >"$@"

update_refs: update_refs_$(branch)_$(YEAR)

update_refs_$(branch)_$(YEAR): hash_file_$(branch).dat hash_cve_bug_$(YEAR).dat
	set -e; pushd "$(KSOURCE_GIT)" >/dev/null ; \
	git checkout -f -B users/$$USER/$(BRANCH)/cve-refs origin/$(BRANCH) 2>/dev/null ; \
	popd >/dev/null
	set -e ; \
	join hash_file_$(branch).dat hash_cve_bug_$(YEAR).dat | \
	while read sha file cve bug ; do \
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

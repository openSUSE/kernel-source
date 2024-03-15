# Expects VULNS_GIT environment variable with a clone of https://git.kernel.org/pub/scm/linux/security/vulns.git
# Expects KSOURCE_GIT environment variable
CVE_TO_BUG=../cve-to-bug.py

YEAR=2024

all: $(YEAR).dat

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

hash_file.dat:
	git --git-dir="$(KSOURCE_GIT)/.git" --work-tree="$(KSOURCE_GIT)" grep -i "^git-commit[[:space:]]*:[[:space:]]*" "$(KSOURCE_GIT)/patches.suse" |\
		awk -vFS=":" '{gsub(" ", "", $$3); print $$3, $$1}' | sort -k1 >"$@"

hash_cve_bug_$(YEAR).dat: hash_cve_$(YEAR).dat cve_bug_$(YEAR).dat
	sort -k 2b,2 hash_cve_$(YEAR).dat | \
	join -1 2 -2 1 -o 1.1,1.2,2.2 - cve_bug_$(YEAR).dat | \
	sort -k 1 >"$@"

update_refs: hash_file_$(branch).dat hash_cve_bug_$(YEAR).dat
	join hash_file_$(branch).dat hash_cve_bug_$(YEAR).dat | \
	while read sha file cve bug ; do \
		pushd "$(KSOURCE_GIT)" >/dev/null ; \
		scripts/add-missing-reference -r $$cve -r "bsc#"$$bug $$file ; \
		popd >/dev/null ; \
	done

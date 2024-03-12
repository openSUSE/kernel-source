# Expects VULNS_GIT environment variable with a clone of https://git.kernel.org/pub/scm/linux/security/vulns.git
# Expects KSOURCE_GIT environment variable

YEAR=2024

all: $(YEAR).dat

hash_cve_$(YEAR).dat: $(wildcard $(VULNS_GIT)/cve/published/$(YEAR)/*.sha1)
	for f in $^ ; do \
		echo $$(head -n1 $$f) $$(basename $${f%.sha1}) ; \
	done | sort -k1 >"$@"

hash_file.dat:
	git --git-dir="$(KSOURCE_GIT)/.git" --work-tree="$(KSOURCE_GIT)" grep -i "^git-commit[[:space:]]*:[[:space:]]*" "$(KSOURCE_GIT)/patches.suse" |\
		awk -vFS=":" '{gsub(" ", "", $$3); print $$3, $$1}' | sort -k1 >"$@"

update_refs: hash_file.dat hash_cve_$(YEAR).dat
	join $^ | while read sha file cve ; do \
		pushd "$(KSOURCE_GIT)" >/dev/null ; \
		scripts/add-missing-reference -r $$cve $$file ; \
		popd >/dev/null ; \
	done

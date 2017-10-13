# from_get
from_get () {
	awk '
		NR==1 && /^From [0-9a-f]+/ {
			print $2
			exit
		}
	'
}

# from_extract
from_extract () {
	awk '
		NR==1 && /^From [0-9a-f]+/ {
			next
		}

		{
			print
		}
	'
}

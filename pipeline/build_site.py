"""Rebuild the public site: take the live index.html as the template and swap in the new data block."""
import json, re, sys
tpl = open(sys.argv[1]).read()   # current index.html
data = {n: json.load(open(f'out/{n}.json'))['rows'] for n in ['status','funds','accumulation','flows','consensus','picker_moves','top_holdings']}
for n in ('top_holdings', 'picker_moves'):
    for r in data[n]: r.pop('key', None)
new = re.sub(r'const D=\{.*?\};\n', lambda m: 'const D=' + json.dumps(data, separators=(',', ':')) + ';\n', tpl, count=1, flags=re.S)
new = re.sub(r'when this was built \(\d+ \w+ \d{4}\)', 'when this was built (' + sys.argv[3] + ')', new)
assert new != tpl or '--force' in sys.argv
open(sys.argv[2], 'w').write(new); print('ok', len(new))

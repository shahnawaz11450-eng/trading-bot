with open('al_fath_v21.py','r') as f:
    lines=f.readlines()

# Find aur remove purana broken meta filter (line 1922 area)
out=[]; skip=False; skip_count=0
for i,line in enumerate(lines):
    # Purana filter start
    if 'from meta_filter import build_meta_filter' in line:
        skip=True; skip_count=0
        print(f"Removing old filter starting line {i+1}")
    # Purana filter end (closing except block)
    if skip:
        skip_count+=1
        if skip_count>15:  # ~15 lines ka block hai
            skip=False
        continue
    out.append(line)

with open('al_fath_v21.py','w') as f:
    f.writelines(out)
print(f"Done. Lines: {len(lines)} -> {len(out)}")

import re
with open('al_fath_v21.py', 'r') as f:
    content = f.read()

# डुप्लीकेट हटाना और साफ़ करना
content = re.sub(r'^\s*exec_gate = ExecutionAlphaGate.*?\n', '', content, flags=re.MULTILINE)
content = re.sub(r'^\s*labeler = LabelEngine.*?\n', '', content, flags=re.MULTILINE)

# सही जगह (logger.info के ऊपर) सही इंडेंटेशन के साथ डालना
new_lines = '    exec_gate = ExecutionAlphaGate(min_edge_bps=50, min_depth_proxy=0.5, max_vol_regime=0.70, block_toxic_flow=True, block_sweeps=True)\n    labeler = LabelEngine(pt_atr=3.0, sl_atr=1.5, horizon=24, ambiguity_mode="pessimistic")\n'
content = content.replace('    logger.info("[L2] Triple Barrier Labels', new_lines + '    logger.info("[L2] Triple Barrier Labels')

with open('al_fath_v21.py', 'w') as f:
    f.write(content)

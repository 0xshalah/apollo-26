// Full PBT profile: P9 runs 10,000 fast-check cases per property.
import { spawnSync } from 'node:child_process';

const result = spawnSync('npx', ['vitest', 'run'], {
  stdio: 'inherit',
  shell: true,
  env: { ...process.env, APOLLO26_PBT_PROFILE: 'full' },
});
process.exit(result.status ?? 1);

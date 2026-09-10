import * as fs from 'fs';
import * as path from 'path';
import * as yaml from 'js-yaml';

export interface CorgiConfig {
  project: string;
  owner: string;
  account: string;
  region: string;

  webDomainName: string;
  serverDomainName: string;
  hostedZoneId: string;
  hostedZoneName: string;
  certificateArn: string;

  allowedIps: string[];

  cpu: number;
  memory: number;
  desiredCount: number;

  dbInstanceType: string;
  dbMultiAz: boolean;
  dbAllocatedStorage: number;
}

interface ConfigFile {
  environments: Record<string, CorgiConfig>;
}

export function loadConfig(stage: string): CorgiConfig {
  const configPath = path.join(__dirname, '..', 'config.yaml');
  const raw = fs.readFileSync(configPath, 'utf8');
  const file = yaml.load(raw) as ConfigFile;

  const config = file.environments[stage];
  if (!config) {
    throw new Error(
      `No config for stage "${stage}". Available: ${Object.keys(file.environments).join(', ')}`,
    );
  }

  config.account = process.env.CDK_DEFAULT_ACCOUNT || process.env.AWS_ACCOUNT_ID || config.account || '';
  config.region = process.env.CDK_DEFAULT_REGION || process.env.AWS_REGION || config.region || 'us-east-1';

  return config;
}

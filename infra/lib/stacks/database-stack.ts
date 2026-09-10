import * as cdk from 'aws-cdk-lib/core';
import * as ec2 from 'aws-cdk-lib/aws-ec2';
import * as rds from 'aws-cdk-lib/aws-rds';
import * as secretsmanager from 'aws-cdk-lib/aws-secretsmanager';
import { Construct } from 'constructs';

export interface DatabaseStackProps extends cdk.StackProps {
  vpc: ec2.Vpc;
  ecsSg: ec2.ISecurityGroup;

  dbInstanceType: string;
  dbMultiAz: boolean;
  dbAllocatedStorage: number;
}

export class DatabaseStack extends cdk.Stack {
  public readonly dbSecret: secretsmanager.ISecret;
  public readonly rdsProxy: rds.DatabaseProxy;
  public readonly rdsProxySg: ec2.SecurityGroup;

  constructor(scope: Construct, id: string, props: DatabaseStackProps) {
    super(scope, id, props);

    const { vpc, ecsSg } = props;

    // RDS security group - only RDS Proxy can reach it
    const rdsSg = new ec2.SecurityGroup(this, 'RdsSg', {
      vpc,
      description: 'RDS instance - accepts from RDS Proxy only',
      allowAllOutbound: false,
    });

    // RDS Proxy security group - only ECS can reach it
    this.rdsProxySg = new ec2.SecurityGroup(this, 'RdsProxySg', {
      vpc,
      description: 'RDS Proxy - accepts from ECS only',
      allowAllOutbound: false,
    });

    // SG chain: ECS -> RDS Proxy -> RDS
    this.rdsProxySg.addIngressRule(ecsSg, ec2.Port.tcp(5432), 'ECS to RDS Proxy');
    this.rdsProxySg.addEgressRule(rdsSg, ec2.Port.tcp(5432), 'RDS Proxy to RDS');
    rdsSg.addIngressRule(this.rdsProxySg, ec2.Port.tcp(5432), 'RDS Proxy to RDS');

    // Database credentials in Secrets Manager
    this.dbSecret = new secretsmanager.Secret(this, 'DbSecret', {
      secretName: 'corgi/database',
      generateSecretString: {
        secretStringTemplate: JSON.stringify({ username: 'corgi_user' }),
        generateStringKey: 'password',
        excludePunctuation: true,
        passwordLength: 32,
      },
    });

    const dbInstance = new rds.DatabaseInstance(this, 'CorgiDb', {
      engine: rds.DatabaseInstanceEngine.postgres({
        version: rds.PostgresEngineVersion.VER_16,
      }),
      instanceType: new ec2.InstanceType(props.dbInstanceType),
      vpc,
      vpcSubnets: { subnetType: ec2.SubnetType.PRIVATE_ISOLATED },
      securityGroups: [rdsSg],
      credentials: rds.Credentials.fromSecret(this.dbSecret),
      databaseName: 'corgi',
      multiAz: props.dbMultiAz,
      allocatedStorage: props.dbAllocatedStorage,
      maxAllocatedStorage: props.dbAllocatedStorage * 2 + 10,
      storageEncrypted: true,
      backupRetention: cdk.Duration.days(7),
      removalPolicy: cdk.RemovalPolicy.SNAPSHOT,
      deletionProtection: false,
    });

    this.rdsProxy = new rds.DatabaseProxy(this, 'CorgiDbProxy', {
      proxyTarget: rds.ProxyTarget.fromInstance(dbInstance),
      secrets: [this.dbSecret],
      vpc,
      vpcSubnets: { subnetType: ec2.SubnetType.PRIVATE_ISOLATED },
      securityGroups: [this.rdsProxySg],
      requireTLS: true,
      dbProxyName: 'corgi-db-proxy',
    });

    new cdk.CfnOutput(this, 'RdsProxyEndpoint', {
      value: this.rdsProxy.endpoint,
    });
  }
}

import * as cdk from 'aws-cdk-lib/core';
import * as ec2 from 'aws-cdk-lib/aws-ec2';
import * as elasticache from 'aws-cdk-lib/aws-elasticache';
import { Construct } from 'constructs';

export interface CacheStackProps extends cdk.StackProps {
  vpc: ec2.Vpc;
  ecsSg: ec2.SecurityGroup;
}

export class CacheStack extends cdk.Stack {
  public readonly redisUrl: string;

  constructor(scope: Construct, id: string, props: CacheStackProps) {
    super(scope, id, props);

    const { vpc, ecsSg } = props;

    const redisSg = new ec2.SecurityGroup(this, 'RedisSg', {
      vpc,
      description: 'Allow ECS tasks to connect to Redis',
    });

    redisSg.addIngressRule(ecsSg, ec2.Port.tcp(6379), 'ECS -> Redis');

    const subnetGroup = new elasticache.CfnSubnetGroup(this, 'RedisSubnetGroup', {
      description: 'Subnets for Corgi Redis',
      subnetIds: vpc.selectSubnets({ subnetType: ec2.SubnetType.PRIVATE_WITH_EGRESS }).subnetIds,
    });

    const redis = new elasticache.CfnCacheCluster(this, 'CorgiRedis', {
      engine: 'redis',
      cacheNodeType: 'cache.t4g.micro',
      numCacheNodes: 1,
      vpcSecurityGroupIds: [redisSg.securityGroupId],
      cacheSubnetGroupName: subnetGroup.ref,
    });

    this.redisUrl = `redis://${redis.attrRedisEndpointAddress}:${redis.attrRedisEndpointPort}/0`;

    new cdk.CfnOutput(this, 'RedisEndpoint', {
      value: this.redisUrl,
    });
  }
}

import os
import subprocess
from aws_cdk import (
    Aws,
    CfnMapping,
    Fn,
    Stack
)
from constructs import Construct

from oe_patterns_cdk_common.alb import Alb
from oe_patterns_cdk_common.amazonmq import RabbitMQ
from oe_patterns_cdk_common.asg import Asg
from oe_patterns_cdk_common.assets_bucket import AssetsBucket
from oe_patterns_cdk_common.aurora_cluster import AuroraPostgresql
from oe_patterns_cdk_common.db_secret import DbSecret
from oe_patterns_cdk_common.dns import Dns
from oe_patterns_cdk_common.elasticache_cluster import ElasticacheRedis
from oe_patterns_cdk_common.secret import Secret
from oe_patterns_cdk_common.ses import Ses
from oe_patterns_cdk_common.util import Util
from oe_patterns_cdk_common.vpc import Vpc

# Begin generated code block
AMI_ID="ami-0d1b64a70e903a941"
AMI_NAME="ordinary-experts-patterns-zulip-alpha-20230511-0622"
generated_ami_ids = {
    "us-east-1": "ami-0d1b64a70e903a941"
}
# End generated code block.

if 'TEMPLATE_VERSION' in os.environ:
    template_version = os.environ['TEMPLATE_VERSION']
else:
    try:
        template_version = subprocess.check_output(["git", "describe"]).strip().decode('ascii')
    except:
        template_version = "CICD"

class ZulipStack(Stack):

    def __init__(self, scope: Construct, id: str, **kwargs) -> None:
        super().__init__(scope, id, **kwargs)

        ami_mapping={ "AMI": { "OEZULIP": AMI_NAME } }
        for region in generated_ami_ids.keys():
            ami_mapping[region] = { "AMI": generated_ami_ids[region] }
        aws_ami_region_map = CfnMapping(
            self,
            "AWSAMIRegionMap",
            mapping=ami_mapping
        )

        # vpc
        vpc = Vpc(self, "Vpc")

        dns = Dns(self, "Dns")

        bucket = AssetsBucket(
            self,
            "AssetsBucket"
        )

        ses = Ses(
            self,
            "Ses",
            hosted_zone_name=dns.route_53_hosted_zone_name_param.value_as_string,
            additional_iam_user_policies=[bucket.user_policy]
        )

        # db_secret
        db_secret = DbSecret(
            self,
            "DbSecret",
            username = "zulip"
        )

        db = AuroraPostgresql(
            self,
            "Db",
            database_name="zulip",
            db_secret=db_secret,
            vpc=vpc
        )

        # REDIS
        redis = ElasticacheRedis(
            self,
            "Redis",
            vpc=vpc
        )

        # RabbitMQ
        secret = Secret(self, "RabbitMQSecret")
        rabbitmq = RabbitMQ(self, "RabbitMQ", secret=secret, vpc=vpc)

        # asg
        with open("zulip/user_data.sh") as f:
            user_data = f.read()
        asg = Asg(
            self,
            "Asg",
            allow_associate_address = True,
            secret_arns=[db_secret.secret_arn(), ses.secret_arn(), secret.secret_arn()],
            use_graviton = False,
            user_data_contents=user_data,
            user_data_variables = {
                "AssetsBucketName": bucket.bucket_name(),
                "DbSecretArn": db_secret.secret_arn(),
                "RabbitMQSecretArn": secret.secret_arn(),
                "Hostname": dns.hostname(),
                "HostedZoneName": dns.route_53_hosted_zone_name_param.value_as_string,
                "InstanceSecretName": Aws.STACK_NAME + "/instance/credentials"
            },
            vpc=vpc
        )
        asg.asg.node.add_dependency(db.db_primary_instance)
        asg.asg.node.add_dependency(rabbitmq.broker)
        asg.asg.node.add_dependency(redis.elasticache_cluster)
        asg.asg.node.add_dependency(ses.generate_smtp_password_custom_resource)

        db_ingress       = Util.add_sg_ingress(db, asg.sg)
        rabbitmq_ingress = Util.add_sg_ingress(rabbitmq, asg.sg)
        redis_ingress    = Util.add_sg_ingress(redis, asg.sg)

        alb = Alb(self, "Alb", asg=asg, vpc=vpc)
        asg.asg.target_group_arns = [ alb.target_group.ref ]

        dns.add_alb(alb)

        # all subdomains should point to the main domain
        # TODO

        parameter_groups = alb.metadata_parameter_group()
        parameter_groups += dns.metadata_parameter_group()
        parameter_groups += asg.metadata_parameter_group()
        parameter_groups += vpc.metadata_parameter_group()

        # AWS::CloudFormation::Interface
        self.template_options.metadata = {
            "OE::Patterns::TemplateVersion": template_version,
            "AWS::CloudFormation::Interface": {
                "ParameterGroups": parameter_groups,
                "ParameterLabels": {
                    **alb.metadata_parameter_labels(),
                    **dns.metadata_parameter_labels(),
                    **asg.metadata_parameter_labels(),
                    **vpc.metadata_parameter_labels()
                }
            }
        }

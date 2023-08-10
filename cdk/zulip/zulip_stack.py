import os
import subprocess
from aws_cdk import (
    aws_iam,
    aws_route53,
    Aws,
    CfnMapping,
    CfnOutput,
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
AMI_ID="ami-0b953ba5c3f6fa525"
AMI_NAME="ordinary-experts-patterns-zulip-alpha-20230715-0222"
generated_ami_ids = {
    "us-east-1": "ami-0b953ba5c3f6fa525"
}
# End generated code block.

if 'TEMPLATE_VERSION' in os.environ:
    template_version = os.environ['TEMPLATE_VERSION']
else:
    try:
        template_version = subprocess.check_output(["git", "describe", "--always"]).strip().decode('ascii')
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

        assets_bucket = AssetsBucket(
            self,
            "AssetsBucket"
        )

        avatars_bucket = AssetsBucket(
            self,
            "AvatarsBucket",
            object_ownership_value = "ObjectWriter",
            remove_public_access_block = True
        )

        ses = Ses(
            self,
            "Ses",
            hosted_zone_name=dns.route_53_hosted_zone_name_param.value_as_string,
            additional_iam_user_policies=[assets_bucket.user_policy, avatars_bucket.user_policy]
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

        asg_update_secret_policy = aws_iam.CfnRole.PolicyProperty(
            policy_document=aws_iam.PolicyDocument(
                statements=[
                    aws_iam.PolicyStatement(
                        effect=aws_iam.Effect.ALLOW,
                        actions=[
                            "secretsmanager:UpdateSecret"
                        ],
                        resources=[
                            f"arn:{Aws.PARTITION}:secretsmanager:{Aws.REGION}:{Aws.ACCOUNT_ID}:secret:{Aws.STACK_NAME}/instance/credentials-*"
                        ]
                    )
                ]
            ),
            policy_name="AllowUpdateInstanceSecret"
        )

        # asg
        with open("zulip/user_data.sh") as f:
            user_data = f.read()
        asg = Asg(
            self,
            "Asg",
            additional_iam_role_policies=[asg_update_secret_policy],
            allow_associate_address = True,
            secret_arns=[db_secret.secret_arn(), ses.secret_arn(), secret.secret_arn()],
            use_graviton = False,
            user_data_contents=user_data,
            user_data_variables = {
                "AssetsBucketName": assets_bucket.bucket_name(),
                "AvatarsBucketName": avatars_bucket.bucket_name(),
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

        alb = Alb(
            self,
            "Alb",
            asg=asg,
            health_check_path = "/elb-check",
            vpc=vpc
        )
        asg.asg.target_group_arns = [ alb.target_group.ref ]

        dns.add_alb(alb)
        # add additional A record for subdomain realm URLs
        subdomain_record_set = aws_route53.CfnRecordSetGroup(
            self,
            "ZulipSubdomainRecordSetGroup",
            hosted_zone_name=f"{dns.route_53_hosted_zone_name_param.value_as_string}.",
            comment=dns.hostname_param.value_as_string,
            record_sets=[
                aws_route53.CfnRecordSetGroup.RecordSetProperty(
                    name=f"*.{dns.hostname_param.value_as_string}.",
                    type="A",
                    alias_target=aws_route53.CfnRecordSetGroup.AliasTargetProperty(
                        dns_name=alb.alb.attr_dns_name,
                        hosted_zone_id=alb.alb.attr_canonical_hosted_zone_id
                    )
                )
            ]
        )
        subdomain_record_set.cfn_options.condition = dns.route_53_hosted_zone_name_exists_condition

        CfnOutput(
            self,
            "FirstUseInstructions",
            description="Instructions for getting started",
            value=f"Visit the URL in the 'initial_new_organization_link' secret value in the '{Aws.STACK_NAME}/instance/credentials' secret in Secrets Manager. This will allow you to create an initial organization and user in Zulip."
        )

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

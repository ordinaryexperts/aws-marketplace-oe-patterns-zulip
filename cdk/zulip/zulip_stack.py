import os
import subprocess
from aws_cdk import (
    CfnMapping,
    Stack
)
from constructs import Construct

from oe_patterns_cdk_common.alb import Alb
from oe_patterns_cdk_common.asg import Asg
from oe_patterns_cdk_common.assets_bucket import AssetsBucket
from oe_patterns_cdk_common.aurora_cluster import AuroraPostgresql
from oe_patterns_cdk_common.db_secret import DbSecret
from oe_patterns_cdk_common.dns import Dns
from oe_patterns_cdk_common.elasticache_cluster import ElasticacheRedis
from oe_patterns_cdk_common.ses import Ses
from oe_patterns_cdk_common.util import Util
from oe_patterns_cdk_common.vpc import Vpc

# Begin generated code block
AMI_ID="ami-05b6754dd2fc08437"
AMI_NAME="ordinary-experts-patterns-zulip-alpha-20221110-0848"
generated_ami_ids = {
    "us-east-1": "ami-05b6754dd2fc08437"
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
            "DbSecret"
        )

        db = AuroraPostgresql(
            self,
            "Db",
            db_secret=db_secret,
            vpc=vpc
        )

        # redis
        redis = ElasticacheRedis(
            self,
            "Redis",
            vpc=vpc
        )

        # asg
        with open("zulip/launch_config_user_data.sh") as f:
            launch_config_user_data = f.read()
        asg = Asg(
            self,
            "Asg",
            allow_associate_address = True,
            default_instance_type = "t3.xlarge",
            secret_arns=[db_secret.secret_arn()],
            user_data_contents=launch_config_user_data,
            user_data_variables = {},
            vpc=vpc
        )
        asg.asg.node.add_dependency(db.db_primary_instance)
        asg.asg.node.add_dependency(ses.generate_smtp_password_custom_resource)

        redis_ingress = Util.add_sg_ingress(redis, asg.sg)
        db_ingress    = Util.add_sg_ingress(db, asg.sg)

        alb = Alb(self, "Alb", asg=asg, vpc=vpc)
        asg.asg.target_group_arns = [ alb.target_group.ref ]

        dns.add_alb(alb)

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

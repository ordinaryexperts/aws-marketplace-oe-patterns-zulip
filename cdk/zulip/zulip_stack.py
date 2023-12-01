import os
import subprocess
from aws_cdk import (
    aws_ec2,
    aws_elasticloadbalancingv2,
    aws_iam,
    aws_route53,
    aws_s3,
    Aws,
    CfnCondition,
    CfnMapping,
    CfnOutput,
    CfnParameter,
    Fn,
    Stack,
    Token
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
AMI_ID="ami-0980adea4bd75302a"
AMI_NAME="ordinary-experts-patterns-zulip-1.0.0-2-g57e1f0b-20231130-0546"
generated_ami_ids = {
    "us-east-1": "ami-0980adea4bd75302a"
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
        CfnMapping(
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
            bucket_label = "Avatars",
            object_ownership_value = "ObjectWriter",
            remove_public_access_block = True
        )

        avatars_bucket_name = Token.as_string(avatars_bucket.assets_bucket.ref)
        avatars_bucket_policy = aws_iam.PolicyStatement(
            actions=["s3:GetObject"],
            resources=[f"arn:aws:s3:::{avatars_bucket_name}/*"],
            principals=[aws_iam.AnyPrincipal()]
        )
        aws_s3.CfnBucketPolicy(
            self,
            "AvatarsBucketPolicy",
            bucket=Token.as_string(avatars_bucket.assets_bucket.ref),
            policy_document=aws_iam.PolicyDocument(statements=[avatars_bucket_policy])
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

        admin_email_param = CfnParameter(
            self,
            "AdminEmail",
            default="",
            description="Optional: The email address to use for the Zulip administrator account. If not specified, 'zulip@{DnsHostname}' will be used."
        )
        giphy_api_key_param = CfnParameter(
            self,
            "GiphyApiKey",
            default="",
            description="Optional: GIPHY API Key. See https://zulip.readthedocs.io/en/stable/production/giphy-gif-integration.html"
        )
        sentry_dsn_param = CfnParameter(
            self,
            "SentryDsn",
            default="",
            description="Optional: Sentry Data Source Name (DSN) endpoint. See https://zulip.readthedocs.io/en/latest/subsystems/logging.html#sentry-error-logging"
        )

        enable_incoming_email_param = CfnParameter(
            self,
            "EnableIncomingEmail",
            allowed_values=[ "true", "false" ],
            default="true",
            description="Required: Enable Incoming Email support. See https://zulip.readthedocs.io/en/stable/production/email-gateway.html"
        )
        enable_mobile_push_notifications_param = CfnParameter(
            self,
            "EnableMobilePushNotifications",
            allowed_values=[ "true", "false" ],
            default="false",
            description="Required: Enable Mobile Push Notification Support. After settings this to 'true' you still need to register your server as described here: https://zulip.readthedocs.io/en/stable/production/mobile-push-notifications.html"
        )
        enable_incoming_email_condition = CfnCondition(
            self,
            "EnableIncomingEmailCondition",
            expression=Fn.condition_equals(enable_incoming_email_param.value, "true")
        )

        # asg
        with open("zulip/user_data.sh") as f:
            user_data = f.read()
        asg = Asg(
            self,
            "Asg",
            additional_iam_role_policies=[asg_update_secret_policy],
            allow_associate_address = True,
            create_and_update_timeout_minutes = 30,
            default_instance_type = 't3.medium',
            excluded_instance_families = ['t2'],
            excluded_instance_sizes = ['nano', 'micro', 'small'],
            secret_arns=[db_secret.secret_arn(), ses.secret_arn(), secret.secret_arn()],
            use_graviton = False,
            user_data_contents=user_data,
            user_data_variables = {
                "AssetsBucketName": assets_bucket.bucket_name(),
                "AvatarsBucketName": avatars_bucket.bucket_name(),
                "DbSecretArn": db_secret.secret_arn(),
                "EnableIncomingEmail": enable_incoming_email_param.value_as_string,
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

        Util.add_sg_ingress(db, asg.sg)
        Util.add_sg_ingress(rabbitmq, asg.sg)
        Util.add_sg_ingress(redis, asg.sg)

        alb = Alb(
            self,
            "Alb",
            asg=asg,
            health_check_path = "/elb-check",
            vpc=vpc
        )

        nlb = aws_elasticloadbalancingv2.CfnLoadBalancer(
            self,
            "Nlb",
            scheme="internet-facing",
            subnets=vpc.public_subnet_ids(),
            type="network"
        )
        nlb.cfn_options.condition = enable_incoming_email_condition
        nlb.add_depends_on(alb.http_listener)
        nlb.add_depends_on(alb.https_listener)

        email_target_group = aws_elasticloadbalancingv2.CfnTargetGroup(
            self,
            "EmailTargetGroup",
            port=25,
            protocol="TCP",
            target_type="instance",
            vpc_id=vpc.id()
        )
        email_target_group.cfn_options.condition = enable_incoming_email_condition

        email_listener = aws_elasticloadbalancingv2.CfnListener(
            self,
            "EmailListener",
            default_actions=[
                aws_elasticloadbalancingv2.CfnListener.ActionProperty(
                    target_group_arn=email_target_group.ref,
                    type="forward"
                )
            ],
            load_balancer_arn=nlb.ref,
            port=25,
            protocol="TCP"
        )
        email_listener.cfn_options.condition = enable_incoming_email_condition

        email_ingress_cidr_param = CfnParameter(
            self,
            "EmailIngressCidr",
            allowed_pattern=r"^((\d{1,3})\.){3}\d{1,3}/\d{1,2}$",
            description="Required (if Enable incoming email is true): VPC IPv4 CIDR block to restrict access to inbound email processing. Set to '0.0.0.0/0' to allow all access, or set to 'X.X.X.X/32' to restrict to one IP (replace Xs with your IP), or set to another CIDR range."
        )

        nlb_http_target_group = aws_elasticloadbalancingv2.CfnTargetGroup(
            self,
            "NlbHttpTargetGroup",
            port=80,
            protocol="TCP",
            target_type="alb",
            targets=[aws_elasticloadbalancingv2.CfnTargetGroup.TargetDescriptionProperty(
                id=alb.alb.ref
            )],
            vpc_id=vpc.id()
        )
        nlb_http_target_group.cfn_options.condition = enable_incoming_email_condition

        nlb_http_listener = aws_elasticloadbalancingv2.CfnListener(
            self,
            "NlbHttpListener",
            default_actions=[
                aws_elasticloadbalancingv2.CfnListener.ActionProperty(
                    target_group_arn=nlb_http_target_group.ref,
                    type="forward"
                )
            ],
            load_balancer_arn=nlb.ref,
            port=80,
            protocol="TCP"
        )
        nlb_http_listener.cfn_options.condition = enable_incoming_email_condition

        nlb_https_target_group = aws_elasticloadbalancingv2.CfnTargetGroup(
            self,
            "NlbHttpsTargetGroup",
            port=443,
            protocol="TCP",
            target_type="alb",
            targets=[aws_elasticloadbalancingv2.CfnTargetGroup.TargetDescriptionProperty(
                id=alb.alb.ref
            )],
            vpc_id=vpc.id()
        )
        nlb_https_target_group.cfn_options.condition = enable_incoming_email_condition

        nlb_https_listener = aws_elasticloadbalancingv2.CfnListener(
            self,
            "NlbHttpsListener",
            default_actions=[
                aws_elasticloadbalancingv2.CfnListener.ActionProperty(
                    target_group_arn=nlb_https_target_group.ref,
                    type="forward"
                )
            ],
            load_balancer_arn=nlb.ref,
            port=443,
            protocol="TCP"
        )
        nlb_https_listener.cfn_options.condition = enable_incoming_email_condition

        asg.asg.add_override(
            "Properties.TargetGroupARNs",
            {
                "Fn::If": [
                    enable_incoming_email_condition.logical_id,
                    [email_target_group.ref, alb.target_group.ref],
                    [alb.target_group.ref]
                ]
            }
        )

        email_sg_ingress = aws_ec2.CfnSecurityGroupIngress(
            self,
            "EmailSgIngress",
            cidr_ip=email_ingress_cidr_param.value_as_string,
            from_port=25,
            group_id=asg.sg.ref,
            ip_protocol="tcp",
            to_port=25
        )
        email_sg_ingress.cfn_options.condition = enable_incoming_email_condition

        # route 53
        record_set = aws_route53.CfnRecordSetGroup(
            self,
            "RecordSetGroup",
            hosted_zone_name=f"{dns.route_53_hosted_zone_name_param.value_as_string}.",
            comment=dns.hostname_param.value_as_string,
            record_sets=[
                aws_route53.CfnRecordSetGroup.RecordSetProperty(
                    name=f"{dns.hostname_param.value_as_string}.",
                    type="A",
                    alias_target=aws_route53.CfnRecordSetGroup.AliasTargetProperty(
                        dns_name=Token.as_string(
                            Fn.condition_if(
                                enable_incoming_email_condition.logical_id,
                                nlb.attr_dns_name,
                                alb.alb.attr_dns_name
                            )
                        ),
                        hosted_zone_id=Token.as_string(
                            Fn.condition_if(
                                enable_incoming_email_condition.logical_id,
                                nlb.attr_canonical_hosted_zone_id,
                                alb.alb.attr_canonical_hosted_zone_id
                            )
                        )
                    )
                )
            ]
        )
        record_set.cfn_options.condition = dns.route_53_hosted_zone_name_exists_condition

        # add additional A record for subdomain realm URLs
        subdomain_record_set = aws_route53.CfnRecordSetGroup(
            self,
            "SubdomainRecordSetGroup",
            hosted_zone_name=f"{dns.route_53_hosted_zone_name_param.value_as_string}.",
            comment=dns.hostname_param.value_as_string,
            record_sets=[
                aws_route53.CfnRecordSetGroup.RecordSetProperty(
                    name=f"*.{dns.hostname_param.value_as_string}.",
                    type="A",
                    alias_target=aws_route53.CfnRecordSetGroup.AliasTargetProperty(
                        dns_name=Token.as_string(
                            Fn.condition_if(
                                enable_incoming_email_condition.logical_id,
                                nlb.attr_dns_name,
                                alb.alb.attr_dns_name
                            )
                        ),
                        hosted_zone_id=Token.as_string(
                            Fn.condition_if(
                                enable_incoming_email_condition.logical_id,
                                nlb.attr_canonical_hosted_zone_id,
                                alb.alb.attr_canonical_hosted_zone_id
                            )
                        )
                    )
                )
            ]
        )
        subdomain_record_set.cfn_options.condition = dns.route_53_hosted_zone_name_exists_condition

        # add MX record to support incoming email
        email_record_set = aws_route53.CfnRecordSet(
            self,
            "EmailRecordSet",
            hosted_zone_name=f"{dns.route_53_hosted_zone_name_param.value_as_string}.",
            name=dns.hostname(),
            resource_records=[
                f"1 {dns.hostname()}."
            ],
            type="MX"
        )
        email_record_set.add_property_override("TTL", 3600)
        email_record_set.cfn_options.condition = enable_incoming_email_condition

        CfnOutput(
            self,
            "SiteUrlOutput",
            description="The URL Endpoint",
            value=f"https://{dns.hostname_param.value_as_string}"
        )

        CfnOutput(
            self,
            "FirstUseInstructions",
            description="Instructions for getting started",
            value="To create an initial organization, connect to the EC2 instance with SSM Sessions Manager. Then run the following command to get a one-time link: sudo su zulip -c '/home/zulip/deployments/current/manage.py generate_realm_creation_link'"
        )

        parameter_groups = [
            {
                "Label": { "default": "Application Config" },
                "Parameters": [
                    admin_email_param.logical_id,
                    giphy_api_key_param.logical_id,
                    enable_mobile_push_notifications_param.logical_id,
                    enable_incoming_email_param.logical_id,
                    email_ingress_cidr_param.logical_id
                ]
            }
        ]
        parameter_groups += alb.metadata_parameter_group()
        parameter_groups += dns.metadata_parameter_group()
        parameter_groups += db.metadata_parameter_group()
        parameter_groups += db_secret.metadata_parameter_group()
        parameter_groups += ses.metadata_parameter_group()
        parameter_groups += assets_bucket.metadata_parameter_group()
        parameter_groups += avatars_bucket.metadata_parameter_group()
        parameter_groups += rabbitmq.metadata_parameter_group()
        parameter_groups += secret.metadata_parameter_group()
        parameter_groups += redis.metadata_parameter_group()
        parameter_groups += asg.metadata_parameter_group()
        parameter_groups += vpc.metadata_parameter_group()

        # AWS::CloudFormation::Interface
        self.template_options.metadata = {
            "OE::Patterns::TemplateVersion": template_version,
            "AWS::CloudFormation::Interface": {
                "ParameterGroups": parameter_groups,
                "ParameterLabels": {
                    admin_email_param.logical_id: {
                        "default": "Zulip Admin Email"
                    },
                    giphy_api_key_param.logical_id: {
                        "default": "GIPHY API Key"
                    },
                    sentry_dsn_param.logical_id: {
                        "default": "Sentry DSN"
                    },
                    enable_mobile_push_notifications_param.logical_id: {
                        "default": "Enable modile push notifications"
                    },
                    enable_incoming_email_param.logical_id: {
                        "default": "Enable incoming email"
                    },
                    email_ingress_cidr_param.logical_id: {
                        "default": "Incoming email ingress CIDR"
                    },
                    **alb.metadata_parameter_labels(),
                    **dns.metadata_parameter_labels(),
                    **db.metadata_parameter_labels(),
                    **db_secret.metadata_parameter_labels(),
                    **ses.metadata_parameter_labels(),
                    **assets_bucket.metadata_parameter_labels(),
                    **avatars_bucket.metadata_parameter_labels(),
                    **rabbitmq.metadata_parameter_labels(),
                    **secret.metadata_parameter_labels(),
                    **redis.metadata_parameter_labels(),
                    **asg.metadata_parameter_labels(),
                    **vpc.metadata_parameter_labels()
                }
            }
        }

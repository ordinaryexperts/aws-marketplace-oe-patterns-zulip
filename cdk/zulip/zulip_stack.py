from aws_cdk import (
    aws_ec2,
    aws_elasticloadbalancingv2,
    aws_iam,
    aws_logs,
    core
)

from oe_patterns_cdk_common.asg import Asg
from oe_patterns_cdk_common.util import Util
from oe_patterns_cdk_common.vpc import Vpc

TWO_YEARS_IN_DAYS=731

# AMI list generated by:
# make AMI_ID=ami-07bb5101b6910f67d ami-ec2-copy
# on Mon Mar 14 19:44:16 UTC 2022.
AMI_ID="ami-07bb5101b6910f67d"
AMI_NAME="test"
generated_ami_ids = {
    "us-east-1": "ami-07bb5101b6910f67d"
}
# End generated code block.

class ZulipStack(core.Stack):

    def __init__(self, scope: core.Construct, id: str, **kwargs) -> None:
        super().__init__(scope, id, **kwargs)

        # vpc
        vpc = Vpc(
            self,
            "Vpc"
        )

        # cloudwatch
        app_log_group = aws_logs.CfnLogGroup(
            self,
            "JitsiAppLogGroup",
            retention_in_days=TWO_YEARS_IN_DAYS
        )
        app_log_group.cfn_options.update_replace_policy = core.CfnDeletionPolicy.RETAIN
        app_log_group.cfn_options.deletion_policy = core.CfnDeletionPolicy.RETAIN
        system_log_group = aws_logs.CfnLogGroup(
            self,
            "JitsiSystemLogGroup",
            retention_in_days=TWO_YEARS_IN_DAYS
        )
        system_log_group.cfn_options.update_replace_policy = core.CfnDeletionPolicy.RETAIN
        system_log_group.cfn_options.deletion_policy = core.CfnDeletionPolicy.RETAIN

        # asg
        with open("zulip/launch_config_user_data.sh") as f:
            launch_config_user_data = f.read()
        asg = Asg(
            self,
            "Zulip",
            allow_associate_address = True,
            default_instance_type = "t3.xlarge",
            log_group_arns = [
                app_log_group.attr_arn,
                system_log_group.attr_arn
            ],
            user_data_contents=launch_config_user_data,
            user_data_variables = {},
            vpc=vpc
        )

        ami_mapping={
            "AMI": {
                "OEZULIP": AMI_NAME
            }
        }
        for region in generated_ami_ids.keys():
            ami_mapping[region] = { "AMI": generated_ami_ids[region] }
        aws_ami_region_map = core.CfnMapping(
            self,
            "AWSAMIRegionMap",
            mapping=ami_mapping
        )


        #
        # PARAMETERS
        #

        certificate_arn_param = core.CfnParameter(
            self,
            "CertificateArn",
            default="",
            description="Optional: Specify the ARN of a ACM Certificate to configure HTTPS."
        )
        alb_ingress_cidr_param = core.CfnParameter(
            self,
            "AlbIngressCidr",
            allowed_pattern="^((\d{1,3})\.){3}\d{1,3}/\d{1,2}$",
            default="0.0.0.0/0",
            description="Optional: VPC IPv4 CIDR block to restrict public access to ALB (default is 0.0.0.0/0 which is open to internet)."
        )

        alb_sg = aws_ec2.CfnSecurityGroup(
            self,
            "AlbSg",
            group_description="{}/AlbSg".format(core.Aws.STACK_NAME),
            vpc_id=vpc.id()
        )
        core.Tags.of(alb_sg).add("Name", "{}/AlbSg".format(core.Aws.STACK_NAME))
        alb_http_ingress = aws_ec2.CfnSecurityGroupIngress(
            self,
            "AlbSgHttpIngress",
            cidr_ip=alb_ingress_cidr_param.value_as_string,
            description="Allow HTTP traffic to ALB from anyone",
            from_port=80,
            group_id=alb_sg.ref,
            ip_protocol="tcp",
            to_port=80
        )
        alb_https_ingress = aws_ec2.CfnSecurityGroupIngress(
            self,
            "AlbSgHttpsIngress",
            cidr_ip=alb_ingress_cidr_param.value_as_string,
            description="Allow HTTPS traffic to ALB from anyone",
            from_port=443,
            group_id=alb_sg.ref,
            ip_protocol="tcp",
            to_port=443
        )
        alb = aws_elasticloadbalancingv2.CfnLoadBalancer(
            self,
            "AppAlb",
            scheme="internet-facing",
            security_groups=[ alb_sg.ref ],
            subnets=vpc.public_subnet_ids(),
            type="application"
        )
        http_listener = aws_elasticloadbalancingv2.CfnListener(
            self,
            "HttpListener",
            # These are updated in the override below to fix case of properties - see below
            default_actions=[
                aws_elasticloadbalancingv2.CfnListener.ActionProperty(
                    redirect_config=aws_elasticloadbalancingv2.CfnListener.RedirectConfigProperty(
                        host="#{host}",
                        path="/#{path}",
                        port="443",
                        protocol="HTTPS",
                        query="#{query}",
                        status_code="HTTP_301"
                    ),
                    type="redirect"
                )
            ],
            load_balancer_arn=alb.ref,
            port=80,
            protocol="HTTP"
        )
        # CDK generates ActionProperty with lowercase properties - need to override due to following error:
        # Stack operations on resource HttpListener would fail starting from 03/01/2021 as the template has invalid properties.
        # Please refer to the resource documentation to fix the template.
        # Properties validation failed for resource HttpListener with message:
        # #/DefaultActions/0: required key [Type] not found
        # #/DefaultActions/0: extraneous key [type] is not permitted
        # #/DefaultActions/0: extraneous key [redirectConfig] is not permitted
        http_listener.add_override(
            "Properties.DefaultActions",
            [
                {
                    'Type': 'redirect',
                    'RedirectConfig': {
                        'Host': "#{host}",
                        'Path': "/#{path}",
                        'Port': "443",
                        'Protocol': "HTTPS",
                        'Query': "#{query}",
                        'StatusCode': "HTTP_301"
                    }
                }
            ]
        )

        https_target_group = aws_elasticloadbalancingv2.CfnTargetGroup(
            self,
            "AsgHttpsTargetGroup",
            health_check_enabled=None,
            health_check_interval_seconds=None,
            port=443,
            protocol="HTTPS",
            target_group_attributes=[
                aws_elasticloadbalancingv2.CfnTargetGroup.TargetGroupAttributeProperty(
                    key='deregistration_delay.timeout_seconds',
                    value='10'
                )
            ],
            target_type="instance",
            vpc_id=vpc.id()
        )
        https_listener = aws_elasticloadbalancingv2.CfnListener(
            self,
            "HttpsListener",
            certificates=[
                aws_elasticloadbalancingv2.CfnListener.CertificateProperty(
                    certificate_arn=certificate_arn_param.value_as_string
                )
            ],
            default_actions=[
                aws_elasticloadbalancingv2.CfnListener.ActionProperty(
                    target_group_arn=https_target_group.ref,
                    type="forward"
                )
            ],
            load_balancer_arn=alb.ref,
            port=443,
            protocol="HTTPS"
        )

#!/usr/bin/env python3
"""
A sample script to create cost report usage per instance type

"""

import argparse
import boto3
import datetime
import operator
import prettytable
import time

import matplotlib.pyplot as plt
from matplotlib import colors

from boto.ec2.instance import Instance
from boto.ec2.ec2object import TaggedEC2Object
import config
from boto.exception import EC2ResponseError


def object_sort_key(obj):
  """
  Key function for sorting collections of EC2 objects.
  :param obj: The object to create a sort key
  :return: A key suitable for sorting, based on the object's configuration
  """
  # TODO(ltd): Move to utils


  if not isinstance(obj, (Instance)):
    return None

  fields = [
    obj.tags.get(config.INSTANCE_ENVIRONMENT_KEY, 'unknown'),
    obj.tags.get(config.INSTANCE_PURPOSE_KEY, 'unknown'),
    obj.id
  ]

  if hasattr(obj, 'cidr_block'):
    fields.insert(2, obj.cidr_block if obj.cidr_block else 'unknown')

  if hasattr(obj, 'availability_zone'):
    fields.insert(2, obj.availability_zone if obj.availability_zone else 'unknown')

  return fields

def create_instance_details_table(instances):
  """
  Create a PrettyTable of the most commonly useful instance details.

  :param instances: A list of instances to generate from
  :return: A PrettyTable object
  """
  # TODO(ltd): Move to utils
  table = prettytable.PrettyTable(['ID', 'Role', 'Hostname', 'State', 'Instance Type',
                                   'Launch date'], sortby='Role', reversesort=True,
                                  sort_key=operator.itemgetter(2, 6))

  table.align['ID'] = 'l'
  table.align['Role'] = 'l'
  table.align['Hostname'] = 'r'
  table.padding_width = 2

  for instance in instances:
    role = generate_role(instance)
    host = generate_host(instance)
    table.add_row([instance.id, role if role else 'unknown', host if host else 'unknown',
                   instance.state, instance.instance_type, instance.launch_time[:10]])

  return table


def generate_role(obj):
  """
  Generates a roledef for an object based on its configured environment and purpose.
  :param obj: The object to generate a roledef
  :return: A roledef string or None if the object is not fully configured
  """
  if isinstance(obj, dict):
    tags = obj.get('Tags', {})
  elif isinstance(obj, TaggedEC2Object):
    tags = obj.tags
  else:
    return None

  if not all([t in tags for t in (config.INSTANCE_ENVIRONMENT_KEY, config.INSTANCE_PURPOSE_KEY)]):
    return None

  return '{environment}_{purpose}'.format(
    environment=tags[config.INSTANCE_ENVIRONMENT_KEY],
    purpose=tags[config.INSTANCE_PURPOSE_KEY].replace('-', '_')
  )

def generate_host(obj, prepend_user=False, use_ip=False, user=None):
  """
  Generates a hostname for an instance based on its configured environment, purpose, and admin user.

  How user works:

  Not prepend_user -> user == ''
  prepend + user provided -> user = provided@
  prepend + no user provided -> user = tags[config.INSTANCE_USER_KEY] + '@'
  prepend + no user provided + no user tag -> ''

  :param obj: The object to generate a hostname (currently only Instances are supported)
  :param prepend_user: Whether the admin user should be prepended to the hostname (i.e. user@domain)
  :param use_ip: Whether or not to use the private IP instead of a generated hostname
  :return: A hostname string or None if the object is not fully configured
  """

  # TODO(ltd): Move to utils

  if not isinstance(obj, (Instance,)):
    return None

  host_user = user or ''
  if prepend_user:
    if user is None and config.INSTANCE_USER_KEY in obj.tags:
      user = obj.tags[config.INSTANCE_USER_KEY]
    if user is not None:
      host_user = user + '@'

  environment = ''
  if config.INSTANCE_ENVIRONMENT_KEY in obj.tags:
    environment = obj.tags[config.INSTANCE_ENVIRONMENT_KEY] + '-'

  purpose = ''
  if config.INSTANCE_PURPOSE_KEY in obj.tags:
    purpose = obj.tags[config.INSTANCE_PURPOSE_KEY] + '-'

  ip = obj.private_ip_address
  identifier = obj.id.split('-')[-1]

  if use_ip:
    return '{user}{ip}'.format(
      user=host_user,
      ip=ip
    )
  else:
    return '{user}{environment}{purpose}{identifier}.{subdomain}'.format(
      user=host_user,
      environment=environment,
      purpose=purpose,
      identifier=identifier,
      subdomain=config.MANAGED_SUBDOMAIN
    )

#!/usr/bin/env python3
"""
A sample script to create cost report usage per instance type

"""

import argparse
import boto3
import datetime
import operator
import time
import utils

import matplotlib.pyplot as plt
from matplotlib import colors

from boto.ec2.instance import Instance
from boto.ec2.ec2object import TaggedEC2Object
import config
from boto.exception import EC2ResponseError


def _query_filters(environment=None, purpose=None, user=None, zone=None):
  filters = []

  if environment:
    filters.append({'Name':'tag:'+config.INSTANCE_ENVIRONMENT_KEY, 'Values':[environment]})
    # filters['tag:' + config.INSTANCE_ENVIRONMENT_KEY] = environment
  if purpose:
    filters.append({'Name':'tag:'+config.INSTANCE_PURPOSE_KEY, 'Values':[purpose]})
    # filters['tag:' + config.INSTANCE_PURPOSE_KEY] = purpose.replace('_', '-')
  if user:
    filters.append({'Name':'tag:'+config.INSTANCE_USER_KEY, 'Values':[user]})
    # filters['tag:' + config.INSTANCE_USER_KEY] = user
  if zone:
    filters.append({'Name':'availabilityZone:', 'Values':[zone]})
    # filters['availabilityZone'] = zone

  return filters

def _instance_query(environment=None, purpose=None, user=None):
  print("Running instance query")
  filters = _query_filters(environment=environment, purpose=purpose, user=user)
  interval_secs = 5
  checks = 0
  max_timeout = 60
  ran = False
  response = None

  while not ran and checks * interval_secs < max_timeout:
    try:
      ec2 = boto3.client('ec2')
      # if filters:
      #   response = ec2.describe_instances(Filters=filters)
      # else:
      response = ec2.describe_instances()
      ran = True
    except EC2ResponseError as error:
      print(error.error_message)
      time.sleep(interval_secs)
    checks = checks + 1
  
  instances = []
  for reservation in response['Reservations']:
    instances.extend(reservation['Instances'])
  return instances


def instance_query(environment=None, purpose=None, user=None, running=False, raw_output=False, fname=None):
  """
  Queries AWS for any instances matching the specified parameters.

  :param environment: The environment associated with matching instances
  :param purpose: The purpose associated with matching instances
  :param user: The administrative user associated with matching instances
  :param running: Whether to match only instances that are currently running
  :param raw_output: Whether the output should only be a list of host names, one per line, or
      a complete table including environment, purpose, role and host.
  :return: A list of boto.ec2.instance.Instance objects
  """

  instances = [
    i for i in _instance_query(environment, purpose, user) if not running or i['State']['Name'] == 'running'
  ]
  
  if not instances:
    print(colors.red('No instances matching specified query.'))
  if environment:
    print('\tenvironment = %s' % environment)
  if purpose:
    print('\tpurpose = %s' % purpose)
  if user:
    print('\tuser = %s' % user)
  elif raw_output:
    for instance in instances:
      print(utils.generate_host(instance))
  else:
    # print(utils.create_instance_details_table(instances).get_string(sortby='Launch date'))
    if fname:
      utils.create_instance_detail_file(instances, fname)

  return instances

def print_pricing_per_instance_type(start, end):
  token = None
  results = []
  while True:
    if token:
      kwargs = {'NextPageToken': token}
    else:
      kwargs = {}
    data = boto3.client('ec2').get_cost_and_usage(TimePeriod={'Start': start, 'End':  end}, Granularity='WEEKLY', Metrics=['UnblendedCost'], GroupBy=[{'Type': 'DIMENSION', 'Key': 'LINKED_ACCOUNT'}, {'Type': 'DIMENSION', 'Key': 'INSTANCE_TYPE'}], **kwargs)
    results += data['ResultsByTime']
    token = data.get('NextPageToken')
    if not token:
      break

  print('\t'.join(['TimePeriod', 'LinkedAccount', 'InstanceType', 'Amount', 'Unit', 'Estimated']))
  for result_by_time in results:
    for group in result_by_time['Groups']:
      amount = group['Metrics']['UnblendedCost']['Amount']
      unit = group['Metrics']['UnblendedCost']['Unit']
      print(result_by_time['TimePeriod']['Start'], '\t', '\t'.join(group['Keys']), '\t', amount, '\t', unit, '\t', result_by_time['Estimated'])


parser = argparse.ArgumentParser()
# parser.add_argument('--days', type=int, default=30)
parser.add_argument('--output_file', type=str, default=None)
parser.add_argument('--env', type=str, default="staging")
args = parser.parse_args()
instance_query(environment=args.env, fname=args.output_file)

# now = datetime.datetime.utcnow()
# start = (now - datetime.timedelta(days=args.days)).strftime('%Y-%m-%d')
# end = now.strftime('%Y-%m-%d')


import boto3
from botocore.exceptions import ClientError
import json

from cubed_tube.lib.util import load_credentials

_cache = {
    'session': None,
    'client': None,
}

CLOUD_CONFIG = load_credentials().cloud_storage

class BucketException(Exception):
    pass

class NoSuchKey(BucketException):
    pass

def get_session(cache=True):
    if cache and _cache['session']:
        return _cache['session']
    session = boto3.Session(
        aws_access_key_id=CLOUD_CONFIG.access_key,
        aws_secret_access_key=CLOUD_CONFIG.secret)
    if cache:
        _cache['session'] = session
    return session

def get_client(session=None, cache=True):
    if cache and _cache['client']:
        return _cache['client']
    session = session or get_session()
    client = session.client('s3', endpoint_url=CLOUD_CONFIG.url)
    if cache:
        _cache['client'] = client
    return client

def list_objects(prefix=None, client=None, bucket=None):
    # NOTE: Max of 1000 objects. Consider adding pagination if this is bad...
    client = client or get_client()
    kwargs = {'Bucket': bucket or CLOUD_CONFIG.name}
    if prefix:
        kwargs['Prefix'] = prefix
    objs = client.list_objects(**kwargs)
    for obj in objs.get('Contents', []):
        yield obj['Key']

def put_object(key: str, value: str, client=None, bucket=None):
    client = client or get_client()
    bucket = bucket or CLOUD_CONFIG.name
    response = client.put_object(Bucket=bucket, Key=key, Body=value)
    response_meta = response.get('ResponseMetadata', {})
    if response_meta.get('HTTPStatusCode', 0)  != 200:
        raise BucketException(
            f"Invalid HTTPStatusCode: {json.dumps(response_meta)}")

def get_object(key: str, client=None, bucket=None):
    client = client or get_client()
    bucket = bucket or CLOUD_CONFIG.name
    try:
        response = client.get_object(Bucket=bucket, Key=key)
        return response['Body'].read()
    except ClientError as e:
        if e.response['Error']['Code'] == 'NoSuchKey':
            raise NoSuchKey(f'Unable to find key {key}')
        raise

def del_objects(keys: list[str], client=None, bucket=None):
    client = client or get_client()
    bucket = bucket or CLOUD_CONFIG.name
    response = client.delete_objects(Bucket=bucket, Delete={
        'Objects': [{'Key': k} for k in keys]})
    response_meta = response.get('ResponseMetadata', {})
    if response_meta.get('HTTPStatusCode', 0)  != 200:
        raise BucketException(
            f"Invalid HTTPStatusCode: {json.dumps(response_meta)}")
    

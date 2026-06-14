"""AWS provider

  - s3_bucket      -> an S3 bucket seeded with one object (durable storage)
  - dynamodb_table -> a DynamoDB table seeded with one row (protected database)

Other resource types are tracked in-process; only these two call AWS. Create and
delete are idempotent, per the Provider contract. 
boto3 is imported lazily (the `aws` extra), so the mock path doesn't require it.
"""
from __future__ import annotations

import boto3
from botocore.exceptions import ClientError

from ..provider import Provider, ResourceState
from ..spec import Resource

_S3 = "s3_bucket"
_DDB = "dynamodb_table"
_GONE = ("404", "NoSuchBucket", "NotFound", "ResourceNotFoundException")


class AwsProvider(Provider):
    def __init__(self, region: str = "us-east-1", prefix: str = "bulwark") -> None:
        self.region = region
        self.prefix = prefix
        self._s3 = boto3.client("s3", region_name=region)
        self._ddb = boto3.client("dynamodb", region_name=region)
        # Ephemeral types: in-process only, no AWS call.
        self._virtual: dict[str, ResourceState] = {}

    # --- dispatch --------------------------------------------------------
    def read(self, resource: Resource) -> ResourceState | None:
        if resource.type == _S3:
            return self._read_bucket(resource)
        if resource.type == _DDB:
            return self._read_table(resource)
        return self._virtual.get(resource.name)

    def create(self, resource: Resource) -> ResourceState:
        if resource.type == _S3:
            return self._create_bucket(resource)
        if resource.type == _DDB:
            return self._create_table(resource)
        state = ResourceState(resource.name, resource.type, f"virtual://{resource.name}", {})
        self._virtual[resource.name] = state
        return state

    def delete(self, state: ResourceState) -> None:
        if state.type == _S3:
            self._delete_bucket(state)
        elif state.type == _DDB:
            self._delete_table(state)
        else:
            self._virtual.pop(state.name, None)

    # --- S3 (durable storage) -------------------------------------------
    def _bucket_name(self, resource: Resource) -> str:
        return resource.config.get("bucket", f"{self.prefix}-{resource.name}")

    def _read_bucket(self, resource: Resource) -> ResourceState | None:
        name = self._bucket_name(resource)
        try:
            self._s3.head_bucket(Bucket=name)
        except ClientError as exc:
            if exc.response["Error"]["Code"] in _GONE:
                return None
            raise
        return ResourceState(resource.name, _S3, name, {"bucket": name})

    def _create_bucket(self, resource: Resource) -> ResourceState:
        existing = self._read_bucket(resource)
        if existing is not None:
            return existing  # idempotent
        name = self._bucket_name(resource)
        kwargs: dict = {"Bucket": name}
        if self.region != "us-east-1":
            kwargs["CreateBucketConfiguration"] = {"LocationConstraint": self.region}
        self._s3.create_bucket(**kwargs)
        self._s3.put_object(Bucket=name, Key="bulwark/seed.txt", Body=b"created by bulwark")
        return ResourceState(resource.name, _S3, name, {"bucket": name})

    def _delete_bucket(self, state: ResourceState) -> None:
        name = state.external_id
        try:
            for obj in self._s3.list_objects_v2(Bucket=name).get("Contents", []):
                self._s3.delete_object(Bucket=name, Key=obj["Key"])
            self._s3.delete_bucket(Bucket=name)
        except ClientError as exc:
            if exc.response["Error"]["Code"] in _GONE:
                return  # already gone — idempotent
            raise

    # --- DynamoDB (protected database) ----------------------------------
    def _table_name(self, resource: Resource) -> str:
        return resource.config.get("table", f"{self.prefix}-{resource.name}")

    def _read_table(self, resource: Resource) -> ResourceState | None:
        name = self._table_name(resource)
        try:
            self._ddb.describe_table(TableName=name)
        except ClientError as exc:
            if exc.response["Error"]["Code"] in _GONE:
                return None
            raise
        return ResourceState(resource.name, _DDB, name, {"table": name})

    def _create_table(self, resource: Resource) -> ResourceState:
        existing = self._read_table(resource)
        if existing is not None:
            return existing  # idempotent
        name = self._table_name(resource)
        self._ddb.create_table(
            TableName=name,
            AttributeDefinitions=[{"AttributeName": "id", "AttributeType": "S"}],
            KeySchema=[{"AttributeName": "id", "KeyType": "HASH"}],
            BillingMode="PAY_PER_REQUEST",
        )
        self._ddb.get_waiter("table_exists").wait(TableName=name)
        self._ddb.put_item(TableName=name, Item={"id": {"S": "seed"}, "note": {"S": "bulwark"}})
        return ResourceState(resource.name, _DDB, name, {"table": name})

    def _delete_table(self, state: ResourceState) -> None:
        try:
            self._ddb.delete_table(TableName=state.external_id)
            self._ddb.get_waiter("table_not_exists").wait(TableName=state.external_id)
        except ClientError as exc:
            if exc.response["Error"]["Code"] in _GONE:
                return  # already gone — idempotent
            raise

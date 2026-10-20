"""Official SDK 2.16.1, two read-only actions, fixed HTTPS endpoints."""
import json
import time
from model import bounds, metric_points, month_key, summarize, bill_summary


class CloudReader:
    def __init__(self, config, access_id, secret, token="", sdk_client=None):
        from aliyunsdkcore.client import AcsClient
        from aliyunsdkcore.auth.credentials import StsTokenCredential
        if not access_id or not secret or max(len(access_id), len(secret), len(token)) > 2048:
            raise ValueError("missing credentials")
        self.config = config
        credential = StsTokenCredential(access_id, secret, token) if token else None
        self.client = sdk_client or AcsClient(ak=access_id, secret=secret, credential=credential,
            region_id="cn-shenzhen", auto_retry=False, connect_timeout=5, timeout=8, verify=True, debug=False)
        self.points = {"in": {}, "out": {}}
        self.month = None

    def call(self, action, params):
        from aliyunsdkcore.request import CommonRequest
        endpoints = {"DescribeMetricList": ("metrics.cn-shenzhen.aliyuncs.com", "2019-01-01", "Cms"),
                     "DescribeInstanceBill": ("business.aliyuncs.com", "2017-12-14", "BssOpenApi")}
        if action not in endpoints:
            raise ValueError("non-read-only action forbidden")
        domain, version, product = endpoints[action]
        request = CommonRequest(domain=domain, version=version, action_name=action, product=product)
        request.set_protocol_type("https")
        request.set_accept_format("json")
        request.set_method("POST")
        request.set_connect_timeout(5)
        request.set_read_timeout(8)
        for key, value in params.items():
            request.add_query_param(key, value)
        data = json.loads(self.client.do_action_with_exception(request))
        if data.get("Success") is not True:
            raise ValueError("cloud query rejected")
        return data

    def metrics(self, now=None):
        now = time.time() if now is None else now
        month = month_key(now)
        if month != self.month:
            self.points = {"in": {}, "out": {}}
            self.month = month
        month_start, _ = bounds(now)
        updates = {}
        for direction in ("in", "out"):
            points = self.points[direction]
            start = max(month_start, max(points, default=month_start) - 300_000)
            params = {"Namespace": "acs_ecs_dashboard",
                "MetricName": "VPC_PublicIP_Internet" + ("InRate" if direction == "in" else "OutRate"),
                "Dimensions": json.dumps({"instanceId": self.config["instance_id"], "ip": self.config["public_ip"]}),
                "Period": "60", "StartTime": str(start), "EndTime": str(int(now * 1000)), "Length": "1440"}
            pages, batch = set(), {}
            for _ in range(32):
                data = self.call("DescribeMetricList", params)
                if str(data.get("Period")) != "60":
                    raise ValueError("unexpected metric period")
                batch.update(metric_points(data, self.config["instance_id"], self.config["public_ip"]))
                cursor = data.get("NextToken")
                if not cursor:
                    break
                if cursor in pages:
                    raise ValueError("repeated page cursor")
                pages.add(cursor)
                params["NextToken"] = cursor
            else:
                raise ValueError("too many metric pages")
            updates[direction] = batch
        for direction in updates:
            self.points[direction].update(updates[direction])
        return {d: summarize(self.points[d], now) for d in ("in", "out")}

    def bills(self, now=None):
        now = time.time() if now is None else now
        params = {"BillingCycle": month_key(now), "ProductCode": "cdt", "IsBillingItem": "false",
                  "Granularity": "MONTHLY", "IsHideZeroCharge": "false", "MaxResults": "300"}
        items, cursors = [], set()
        for _ in range(20):
            data = self.call("DescribeInstanceBill", params)["Data"]
            if data.get("BillingCycle") != params["BillingCycle"] or not isinstance(data.get("Items"), list):
                raise ValueError("invalid billing response")
            items.extend(data["Items"])
            cursor = data.get("NextToken")
            if not cursor:
                return bill_summary(items, self.config["instance_id"])
            if cursor in cursors:
                raise ValueError("repeated billing cursor")
            cursors.add(cursor)
            params["NextToken"] = cursor
        raise ValueError("too many billing pages")

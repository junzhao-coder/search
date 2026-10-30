"""Platform access: bounded, evidence-first adapters.

Shared skeleton for Zhihu (this batch) and the platforms that follow
(Weibo -> Douyin -> Tieba). Only two things are generic here: the durable call
budget and the URL/record hygiene rules. Parsing stays per platform.
"""

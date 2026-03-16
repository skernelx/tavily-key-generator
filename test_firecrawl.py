#!/usr/bin/env python3
"""
Firecrawl 注册功能测试脚本
"""
import sys
import os

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from mail_provider import create_email
from firecrawl_core import register

def test_firecrawl_registration():
    """测试 Firecrawl 注册流程"""
    print("=" * 60)
    print("Firecrawl 注册测试")
    print("=" * 60)

    # 创建邮箱
    email, password = create_email(service="firecrawl")
    print(f"\n📧 测试邮箱: {email}")
    print(f"🔑 测试密码: {password}")

    # 执行注册
    print("\n开始注册流程...\n")
    result = register(email, password)

    # 输出结果
    print("\n" + "=" * 60)
    if result and result != "SUCCESS_NO_KEY":
        print("✅ 测试成功！")
        print(f"API Key: {result}")
    elif result == "SUCCESS_NO_KEY":
        print("⚠️  注册成功但未获取到 API Key")
    else:
        print("❌ 测试失败")
    print("=" * 60)

    return result

if __name__ == "__main__":
    test_firecrawl_registration()

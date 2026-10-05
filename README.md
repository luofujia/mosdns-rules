1.FORK项目私有

2.Cloudflare：创建 KV

名称：

YOUTUBE_ADS

复制：

Namespace ID

3. 修改 wrangler.toml

把：

id = "YOUR_KV_NAMESPACE_ID"

改成：

id = "你的真实KV ID"

pattern = "ad.baidu.com"填写自定义域名

4. 创建 Cloudflare API Token

需要让 GitHub Actions 能：

部署 Worker
+
读写 KV

然后 GitHub：

Settings
→ Secrets and variables
→ Actions

添加：

CLOUDFLARE_API_TOKEN

CLOUDFLARE_ACCOUNT_ID

5.第一次运行

GitHub：

Actions
→ Update MOSDNS Rules
→ Run workflow

6.最终访问地址

你原来的域名：

https://ad.baidu.com

测试：

/health

/status

/meta.json

/rules.txt

/youtube_ads_domains.txt

其中 MOSDNS 最终只需要：

https://ad.baidu.com/rules.txt

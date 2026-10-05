const JSON_HEADERS = {
  "Content-Type": "application/json; charset=utf-8",
  "Cache-Control": "public, max-age=300",
  "Access-Control-Allow-Origin": "*",
};

const TEXT_HEADERS = {
  "Content-Type": "text/plain; charset=utf-8",
  "Cache-Control": "public, max-age=300",
  "Access-Control-Allow-Origin": "*",
};

function json(data, status = 200) {
  return new Response(
    JSON.stringify(data, null, 2),
    {
      status,
      headers: JSON_HEADERS,
    }
  );
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const path = url.pathname;

    try {
      // ==========================================
      // 首页
      // ==========================================

      if (path === "/" || path === "") {
        return new Response(
          [
            "MOSDNS Rule Server",
            "",
            "Endpoints:",
            "/rules.txt",
            "/youtube_ads_domains.txt",
            "/meta.json",
            "/status",
            "/health",
          ].join("\n") + "\n",
          {
            status: 200,
            headers: TEXT_HEADERS,
          }
        );
      }

      // ==========================================
      // Health
      // ==========================================

      if (path === "/health") {
        return json({
          ok: true,
          service: "mosdns-rules",
          time: new Date().toISOString(),
        });
      }

      // ==========================================
      // Meta
      // ==========================================

      if (path === "/meta.json") {
        const value = await env.YOUTUBE_ADS.get(
          "meta.json",
          {
            type: "text",
            cacheTtl: 300,
          }
        );

        if (!value) {
          return json(
            {
              ok: false,
              error: "meta.json not found",
            },
            404
          );
        }

        return new Response(value, {
          status: 200,
          headers: JSON_HEADERS,
        });
      }

      // ==========================================
      // Status
      // ==========================================

      if (path === "/status") {
        const manifest =
          await env.YOUTUBE_ADS.get(
            "rules_manifest.json",
            {
              type: "json",
              cacheTtl: 300,
            }
          );

        const meta =
          await env.YOUTUBE_ADS.get(
            "meta.json",
            {
              type: "json",
              cacheTtl: 300,
            }
          );

        return json({
          ok: !!manifest,
          manifest: manifest || null,
          meta: meta || null,
        });
      }

      // ==========================================
      // YouTube 专用规则
      // ==========================================

      if (path === "/youtube_ads_domains.txt") {
        const stream =
          await env.YOUTUBE_ADS.get(
            "youtube_ads_domains.txt",
            {
              type: "stream",
              cacheTtl: 300,
            }
          );

        if (!stream) {
          return new Response(
            "youtube_ads_domains.txt not found\n",
            {
              status: 404,
              headers: TEXT_HEADERS,
            }
          );
        }

        return new Response(stream, {
          status: 200,
          headers: TEXT_HEADERS,
        });
      }

      // ==========================================
      // 总规则
      // ==========================================

      if (path === "/rules.txt") {
        const manifest =
          await env.YOUTUBE_ADS.get(
            "rules_manifest.json",
            {
              type: "json",
              cacheTtl: 300,
            }
          );

        if (!manifest) {
          return new Response(
            "rules_manifest.json not found\n",
            {
              status: 503,
              headers: TEXT_HEADERS,
            }
          );
        }

        const prefix = manifest.prefix;
        const count = Number(manifest.count);

        if (
          typeof prefix !== "string" ||
          !prefix ||
          !Number.isInteger(count) ||
          count < 1 ||
          count > 1000
        ) {
          return new Response(
            "Invalid rules manifest\n",
            {
              status: 500,
              headers: TEXT_HEADERS,
            }
          );
        }

        // ========================================
        // 流式拼接所有 KV 分片
        // ========================================

        const stream = new ReadableStream({
          async start(controller) {
            try {
              for (let i = 0; i < count; i++) {
                const key =
                  `${prefix}/${String(i).padStart(5, "0")}`;

                const chunk =
                  await env.YOUTUBE_ADS.get(
                    key,
                    {
                      type: "stream",
                      cacheTtl: 300,
                    }
                  );

                if (!chunk) {
                  throw new Error(
                    `Missing KV chunk: ${key}`
                  );
                }

                const reader =
                  chunk.getReader();

                try {
                  while (true) {
                    const result =
                      await reader.read();

                    if (result.done) {
                      break;
                    }

                    controller.enqueue(
                      result.value
                    );
                  }
                } finally {
                  reader.releaseLock();
                }
              }

              controller.close();

            } catch (error) {
              controller.error(error);
            }
          },
        });

        return new Response(stream, {
          status: 200,
          headers: {
            ...TEXT_HEADERS,
            "Content-Disposition":
              'inline; filename="rules.txt"',
          },
        });
      }

      // ==========================================
      // /update
      //
      // Worker Free 不负责更新
      // GitHub Actions 才负责更新
      // ==========================================

      if (path === "/update") {
        return json(
          {
            ok: false,
            message:
              "Updates are performed by GitHub Actions.",
          },
          405
        );
      }

      // ==========================================
      // 404
      // ==========================================

      return new Response(
        "Not Found\n",
        {
          status: 404,
          headers: TEXT_HEADERS,
        }
      );

    } catch (error) {
      return json(
        {
          ok: false,
          error: String(error),
        },
        500
      );
    }
  },
};

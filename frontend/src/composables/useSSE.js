/**
 * SSE ReadableStream 解析器。
 * 用法: await consumeSSE(response, (event) => { ... })
 * 兼容 \r\n / \n / \r 三种行分隔符。
 */
export function consumeSSE(response, onEvent) {
  return new Promise(async (resolve, reject) => {
    try {
      if (!response.ok) {
        const text = await response.text().catch(() => '')
        throw new Error(`HTTP ${response.status}: ${text.slice(0, 200)}`)
      }
      if (!response.body) {
        throw new Error('浏览器不支持 ReadableStream')
      }

      const reader = response.body.getReader()
      const decoder = new TextDecoder('utf-8')
      let buffer = ''

      const blockSplit = /\r?\n\r?\n|\n\n/
      const lineSplit = /\r?\n/

      const parseBlock = (block) => {
        for (const line of block.split(lineSplit)) {
          if (line.startsWith('data:')) {
            const payload = line.slice(5).trim()
            if (!payload) continue
            try {
              onEvent(JSON.parse(payload))
            } catch (e) {
              console.warn('[SSE] JSON parse error:', payload, e)
            }
          }
        }
      }

      while (true) {
        const { done, value } = await reader.read()
        if (done) {
          if (buffer.trim()) parseBlock(buffer)
          resolve()
          break
        }
        buffer += decoder.decode(value, { stream: true })

        const parts = buffer.split(blockSplit)
        buffer = parts.pop()
        for (const block of parts) parseBlock(block)
      }
    } catch (e) {
      reject(e)
    }
  })
}

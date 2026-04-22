/**
 * n8n 외부 훅 (Custom Hooks)
 * 워크플로우 실행 전/후 이벤트를 처리합니다.
 * 참고: https://docs.n8n.io/hosting/configuration/configuration-examples/
 */

module.exports = {
  /**
   * 워크플로우 실행 시작 시 호출
   */
  workflowExecuteBefore: [
    async function (workflowData) {
      console.log(`[CMP] 워크플로우 시작: ${workflowData.name} (${new Date().toISOString()})`);
    },
  ],

  /**
   * 워크플로우 실행 완료 시 호출
   */
  workflowExecuteAfter: [
    async function (workflowData, runData) {
      const status = runData.status;
      const name = workflowData.name;
      const duration = runData.stoppedAt
        ? new Date(runData.stoppedAt) - new Date(runData.startedAt)
        : null;

      console.log(
        `[CMP] 워크플로우 완료: ${name} | 상태: ${status} | 소요시간: ${duration ? duration + 'ms' : 'N/A'}`
      );

      // 실패 시 Slack 알림 (SLACK_WEBHOOK_URL 환경변수 필요)
      if (status === 'error' && process.env.SLACK_WEBHOOK_URL) {
        try {
          const https = require('https');
          const payload = JSON.stringify({
            text: `❌ [CMP 파이프라인 오류]\n워크플로우: ${name}\n시간: ${new Date().toLocaleString('ko-KR', { timeZone: 'Asia/Seoul' })}`,
          });

          const url = new URL(process.env.SLACK_WEBHOOK_URL);
          const options = {
            hostname: url.hostname,
            path: url.pathname,
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              'Content-Length': Buffer.byteLength(payload),
            },
          };

          const req = https.request(options);
          req.write(payload);
          req.end();
        } catch (e) {
          console.error('[CMP] Slack 알림 전송 실패:', e.message);
        }
      }
    },
  ],
};

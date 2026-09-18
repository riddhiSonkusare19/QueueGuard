// Simulates a ticket-drop style traffic surge hitting the Queue Service.
//
// Run with:  k6 run surge.js
// Or against a specific target:
//   k6 run -e QUEUE_URL=http://<queue-service-external-ip>:8001 surge.js
//
// Install k6: https://k6.io/docs/get-started/installation/

import http from 'k6/http';
import { check, sleep } from 'k6';

const QUEUE_URL = __ENV.QUEUE_URL || 'http://localhost:8001';
const EVENT_ID = __ENV.EVENT_ID || 'surge-demo';

export const options = {
  scenarios: {
    ticket_drop_surge: {
      executor: 'ramping-vus',
      startVUs: 0,
      stages: [
        { duration: '10s', target: 50 },   // warm-up
        { duration: '20s', target: 500 },  // the surge - this is the moment
        { duration: '60s', target: 500 },  // sustained peak - watch the dashboard here
        { duration: '20s', target: 0 },    // drain off
      ],
    },
  },
  thresholds: {
    http_req_failed: ['rate<0.5'],   // the queue is allowed to be slow under surge, not allowed to fully fall over
  },
};

export default function () {
  const userId = `user-${__VU}-${__ITER}`;

  const res = http.post(
    `${QUEUE_URL}/queue/join`,
    JSON.stringify({ user_id: userId, event_id: EVENT_ID }),
    { headers: { 'Content-Type': 'application/json' } }
  );

  check(res, {
    'join succeeded (2xx)': (r) => r.status >= 200 && r.status < 300,
  });

  sleep(Math.random() * 2);
}

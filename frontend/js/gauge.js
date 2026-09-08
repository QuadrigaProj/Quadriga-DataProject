/* 체력나이 게이지 — 로고가 곧 데이터다.
 *
 * 눈금 읽는 법
 *   왼쪽 끝(약 7시)   = 0세
 *   오른쪽 끝(약 5시) = **처음 기록한 체력나이** (기준점)
 *   초록 채움         = 0세 → 목표 체력나이
 *   주황 점           = 지금 체력나이
 *   점이 밑바닥 한가운데 = 처음보다 나빠졌다는 뜻 (눈금 밖)
 *
 * 오른쪽 끝을 실제 나이로 두면 눈금이 1년에 한 칸씩 멋대로 움직인다.
 * 처음 기록을 기준으로 두면 점이 왼쪽으로 갈수록 좋아진 것이고,
 * 그 거리가 곧 "앱을 쓰면서 얼마나 나아졌나" 가 된다.
 *
 * 좌표는 로고 원본(1024x1024)을 픽셀 단위로 계측한 값이다. 건드리지 말 것.
 */
const GAUGE = (() => {
  const CX = 511.5, CY = 512, R = 268, SW = 103;
  const A0 = 124.1, SWEEP = 291.9;        // 시작 각도와 전체 호 길이(도)
  const OVER_ANGLE = 90;                  // 눈금 밖 — 원의 밑바닥 한가운데
  const DOT_ORBIT = 0.873 * R;            // 점은 링 중심선보다 살짝 안쪽을 돈다
  const DOT_R = 71.5, HALO = 97.5;        // 점 반지름과 그 둘레의 여백
  const GREEN = '#12B76A', TRACK = '#E4DACA', DOT = '#F2704B';

  // 데이터가 없을 때(로그인 전 등) 보여줄 기본 비율 = 로고 원본 그대로
  const DEFAULT = { green: 0.7743, dot: 0.6214 };

  let seq = 0;

  const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v));
  const pt = (deg, r) => {
    const t = deg * Math.PI / 180;
    return [CX + r * Math.cos(t), CY + r * Math.sin(t)];
  };

  function arc(a0, a1) {
    if (a1 - a0 < 0.05) return '';
    const [x0, y0] = pt(a0, R), [x1, y1] = pt(a1, R);
    const large = (a1 - a0) > 180 ? 1 : 0;
    return `M ${x0.toFixed(2)} ${y0.toFixed(2)} A ${R} ${R} 0 ${large} 1 ${x1.toFixed(2)} ${y1.toFixed(2)}`;
  }

  /* green·dot 은 0~1 비율. dot 이 1 을 넘으면 눈금 밖으로 뺀다. */
  function svg(green, dot, id) {
    const gEnd = A0 + clamp(green, 0, 1) * SWEEP;
    const end  = A0 + SWEEP;
    const dotAngle = dot > 1 ? OVER_ANGLE : A0 + clamp(dot, 0, 1) * SWEEP;
    const [dx, dy] = pt(dotAngle, DOT_ORBIT);

    const paths = [];
    if (gEnd < end)  paths.push(`<path d="${arc(gEnd, end)}" stroke="${TRACK}"/>`);
    if (gEnd > A0)   paths.push(`<path d="${arc(A0, gEnd)}" stroke="${GREEN}"/>`);

    return `<svg viewBox="0 0 1024 1024" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="체력나이 게이지">
  <mask id="${id}">
    <rect width="1024" height="1024" fill="#fff"/>
    <circle cx="${dx.toFixed(2)}" cy="${dy.toFixed(2)}" r="${HALO}" fill="#000"/>
  </mask>
  <g fill="none" stroke-width="${SW}" mask="url(#${id})">
    ${paths.join('\n    ')}
  </g>
  <circle cx="${dx.toFixed(2)}" cy="${dy.toFixed(2)}" r="${DOT_R}" fill="${DOT}"/>
</svg>`;
  }

  /* 기준나이·체력나이·목표 → 비율. 값이 없으면 로고 원본 비율로 돌아간다.
     baseAge 는 오른쪽 끝 = 처음 기록한 체력나이. */
  function ratios({ baseAge, fitnessAge, targetAge } = {}) {
    if (!baseAge || baseAge <= 0) return { ...DEFAULT, known: false };
    return {
      green: targetAge ? clamp(targetAge / baseAge, 0, 1) : DEFAULT.green,
      dot: fitnessAge ? fitnessAge / baseAge : DEFAULT.dot,
      known: !!fitnessAge,
    };
  }

  const easeOut = (t) => 1 - Math.pow(1 - t, 3);

  function render(el, data, { animate = false, duration = 900 } = {}) {
    if (!el) return;
    const { green, dot } = ratios(data);
    const id = 'gm' + (++seq);
    if (!animate) { el.innerHTML = svg(green, dot, id); return; }

    // 0 에서 차오른다. 점도 왼쪽 끝에서 같이 출발한다.
    const t0 = performance.now();
    (function step(now) {
      const t = easeOut(clamp((now - t0) / duration, 0, 1));
      el.innerHTML = svg(green * t, dot * t, id);
      if (t < 1) requestAnimationFrame(step);
    })(t0);
  }

  return { render, ratios };
})();

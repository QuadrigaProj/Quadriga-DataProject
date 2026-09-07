/* 운동 그림 (H7) — 두 종류를 한 파일에 모은다.
 *   1. 자세  사람이 그 동작을 하는 모습. 기구만 그리면 어떻게 쓰는지 알 수 없다.
 *            (푸시업은 아령이 아니라 엎드린 사람이어야 한다)
 *   2. 요인  무엇을 늘리는 운동인지 — 유연성 · 근력 · 심폐지구력 · 근지구력.
 *
 * SVG <symbol> 스프라이트를 문서에 한 번 심고 <use> 로 꺼내 쓴다. 파일이 38개로
 * 늘어나지 않고, 색은 currentColor 라 쓰는 자리에서 정한다.
 */
const MOVE_ART = (() => {
  const SPRITE = `
<svg xmlns="http://www.w3.org/2000/svg" width="0" height="0" style="position:absolute" aria-hidden="true">
  <symbol id="pose-squat" viewBox="0 0 64 64"><circle cx='30' cy='14' r='6'/><path d='M30 20 V34'/><path d='M30 34 L20 44 V56'/><path d='M30 34 L40 44 V56'/><path d='M30 24 L48 22'/></symbol>
  <symbol id="pose-pushup" viewBox="0 0 64 64"><circle cx='14' cy='26' r='6'/><path d='M20 28 L50 40'/><path d='M23 29 V48 M47 38 V48'/><path d='M8 48 H58'/><path d='M33 12 V24 M29 19 L33 25 L37 19'/></symbol>
  <symbol id="pose-knee-pushup" viewBox="0 0 64 64"><circle cx='14' cy='26' r='6'/><path d='M20 28 L42 37'/><path d='M23 29 V48'/><path d='M42 37 L45 46 H56'/><path d='M8 48 H58'/></symbol>
  <symbol id="pose-lunge" viewBox="0 0 64 64"><circle cx='30' cy='12' r='6'/><path d='M30 18 V32'/><path d='M30 32 L18 44 V56'/><path d='M30 32 L44 42 L52 56'/></symbol>
  <symbol id="pose-plank" viewBox="0 0 64 64"><circle cx='14' cy='30' r='6'/><path d='M20 33 L52 42'/><path d='M23 34 V47 H12'/><path d='M50 41 V48'/><path d='M8 48 H58'/></symbol>
  <symbol id="pose-crunch" viewBox="0 0 64 64"><circle cx='20' cy='26' r='6'/><path d='M25 30 L36 38'/><path d='M36 38 L48 30 V44'/><path d='M36 38 L44 46'/><path d='M8 48 H58'/></symbol>
  <symbol id="pose-bridge" viewBox="0 0 64 64"><circle cx='12' cy='40' r='6'/><path d='M18 40 Q32 22 42 40'/><path d='M42 40 V52'/><path d='M8 52 H58'/></symbol>
  <symbol id="pose-burpee" viewBox="0 0 64 64"><circle cx='22' cy='20' r='6'/><path d='M22 26 L28 38'/><path d='M28 38 L18 48'/><path d='M28 38 L42 44 L50 50'/><path d='M8 50 H58'/><path d='M34 12 L40 6 M44 14 L52 10'/></symbol>
  <symbol id="pose-bench-press" viewBox="0 0 64 64"><circle cx='16' cy='34' r='5'/><path d='M21 36 H44'/><path d='M28 36 V26 M40 36 V26'/><path d='M18 24 H50'/><path d='M18 20 V28 M50 20 V28'/><path d='M44 36 L52 48'/><path d='M12 48 H56'/></symbol>
  <symbol id="pose-deadlift" viewBox="0 0 64 64"><circle cx='26' cy='14' r='6'/><path d='M26 20 Q30 28 32 32'/><path d='M32 32 V56'/><path d='M32 32 L26 44'/><path d='M14 44 H50'/><path d='M14 40 V48 M50 40 V48'/></symbol>
  <symbol id="pose-barbell-squat" viewBox="0 0 64 64"><circle cx='30' cy='16' r='6'/><path d='M14 24 H50'/><path d='M14 20 V28 M50 20 V28'/><path d='M30 24 V36'/><path d='M30 36 L20 46 V56'/><path d='M30 36 L40 46 V56'/></symbol>
  <symbol id="pose-lat-pulldown" viewBox="0 0 64 64"><circle cx='30' cy='26' r='6'/><path d='M30 32 V44'/><path d='M30 44 L22 56 M30 44 L38 56'/><path d='M22 12 H38'/><path d='M24 14 L30 30 M36 14 L30 30'/></symbol>
  <symbol id="pose-leg-press" viewBox="0 0 64 64"><circle cx='16' cy='36' r='5'/><path d='M21 38 L32 42'/><path d='M32 42 L44 32 L52 26'/><path d='M46 18 L56 34'/><path d='M10 48 H40'/></symbol>
  <symbol id="pose-dumbbell-curl" viewBox="0 0 64 64"><circle cx='30' cy='14' r='6'/><path d='M30 20 V40 M30 40 L24 56 M30 40 L36 56'/><path d='M30 26 L40 32 L36 22'/><path d='M32 18 H40 M34 16 V24 M38 16 V24'/></symbol>
  <symbol id="pose-shoulder-press" viewBox="0 0 64 64"><circle cx='30' cy='24' r='6'/><path d='M30 30 V42 M30 42 L24 56 M30 42 L36 56'/><path d='M16 12 H44'/><path d='M16 8 V16 M44 8 V16'/><path d='M22 13 L28 26 M38 13 L32 26'/></symbol>
  <symbol id="pose-kettlebell-swing" viewBox="0 0 64 64"><circle cx='26' cy='16' r='6'/><path d='M26 22 Q30 30 32 34'/><path d='M32 34 L26 46 V56 M32 34 L40 46 V56'/><path d='M32 30 L48 24'/><circle cx='51' cy='21' r='5'/></symbol>
  <symbol id="pose-walk" viewBox="0 0 64 64"><circle cx='30' cy='12' r='6'/><path d='M30 18 V36'/><path d='M30 36 L22 50 V56'/><path d='M30 36 L40 48 V56'/><path d='M30 24 L22 32 M30 24 L40 30'/></symbol>
  <symbol id="pose-run" viewBox="0 0 64 64"><circle cx='32' cy='12' r='6'/><path d='M32 18 L28 34'/><path d='M28 34 L16 44 L18 54'/><path d='M28 34 L42 40 L46 54'/><path d='M31 22 L18 26 M31 22 L46 20'/></symbol>
  <symbol id="pose-treadmill" viewBox="0 0 64 64"><circle cx='26' cy='14' r='5'/><path d='M26 19 L24 32'/><path d='M24 32 L16 42 M24 32 L32 40'/><path d='M25 24 L36 22'/><path d='M10 48 H50 M50 48 V26 H42'/></symbol>
  <symbol id="pose-cycle" viewBox="0 0 64 64"><circle cx='34' cy='12' r='5'/><path d='M34 17 L30 28'/><path d='M30 28 L22 38 M30 28 L38 34'/><circle cx='16' cy='46' r='8'/><circle cx='46' cy='46' r='8'/><path d='M16 46 L30 34 L46 46 M30 34 L38 28'/></symbol>
  <symbol id="pose-rowing" viewBox="0 0 64 64"><circle cx='22' cy='20' r='5'/><path d='M22 25 L26 36'/><path d='M26 36 L38 40 L48 36'/><path d='M26 36 L18 44'/><path d='M10 50 H54'/><path d='M14 44 H30'/></symbol>
  <symbol id="pose-jump-rope" viewBox="0 0 64 64"><circle cx='32' cy='16' r='6'/><path d='M32 22 V38 M32 38 L26 52 M32 38 L38 52'/><path d='M32 28 H20 M32 28 H44'/><path d='M20 28 Q6 40 32 56 Q58 40 44 28'/></symbol>
  <symbol id="pose-stair" viewBox="0 0 64 64"><circle cx='24' cy='14' r='6'/><path d='M24 20 V34'/><path d='M24 34 L16 48 V54'/><path d='M24 34 L36 38 L38 46'/><path d='M8 54 H30 V44 H42 V34 H56'/></symbol>
  <symbol id="pose-swim" viewBox="0 0 64 64"><circle cx='18' cy='30' r='5'/><path d='M23 32 H44'/><path d='M44 32 L54 40'/><path d='M20 26 Q28 14 38 22'/><path d='M8 44 Q18 40 28 44 T48 44'/></symbol>
  <symbol id="pose-hamstring-stretch" viewBox="0 0 64 64"><circle cx='20' cy='24' r='6'/><path d='M25 28 L34 34'/><path d='M34 34 H52'/><path d='M34 34 L44 30'/><path d='M52 34 V28'/><path d='M8 44 H58'/></symbol>
  <symbol id="pose-calf-stretch" viewBox="0 0 64 64"><circle cx='24' cy='16' r='6'/><path d='M24 22 L28 34'/><path d='M28 34 L20 48 V54'/><path d='M28 34 L40 46 L46 54'/><path d='M26 26 L46 20'/><path d='M50 8 V54'/></symbol>
  <symbol id="pose-shoulder-stretch" viewBox="0 0 64 64"><circle cx='30' cy='14' r='6'/><path d='M30 20 V40 M30 40 L24 56 M30 40 L36 56'/><path d='M30 26 H48'/><path d='M44 22 Q52 26 44 32'/></symbol>
  <symbol id="pose-hip-stretch" viewBox="0 0 64 64"><circle cx='26' cy='18' r='6'/><path d='M26 24 V36'/><path d='M26 36 L14 48 H26'/><path d='M26 36 L44 44 L52 52'/><path d='M8 52 H58'/></symbol>
  <symbol id="pose-twist" viewBox="0 0 64 64"><circle cx='14' cy='34' r='5'/><path d='M19 36 H36'/><path d='M36 36 Q44 36 44 46 L52 50'/><path d='M20 30 H34 M20 42 H30'/><path d='M8 52 H58'/></symbol>
  <symbol id="pose-neck-stretch" viewBox="0 0 64 64"><circle cx='32' cy='18' r='7'/><path d='M32 25 V42 M32 42 L26 56 M32 42 L38 56'/><path d='M32 30 L44 22 Q40 14 34 14'/><path d='M26 12 Q30 8 36 10'/></symbol>
  <symbol id="pose-deep-breath" viewBox="0 0 64 64"><circle cx='32' cy='18' r='6'/><path d='M32 24 V40'/><path d='M32 40 L18 50 H46 Z'/><path d='M32 28 L20 34 M32 28 L44 34'/><path d='M44 12 Q52 16 44 20 M50 8 Q60 14 50 20'/></symbol>
  <symbol id="pose-one-leg" viewBox="0 0 64 64"><circle cx='30' cy='12' r='6'/><path d='M30 18 V36'/><path d='M30 36 V56'/><path d='M30 36 L42 44 L44 32'/><path d='M30 24 L16 18 M30 24 L44 18'/><path d='M18 56 H46'/></symbol>
  <symbol id="pose-side-plank" viewBox="0 0 64 64"><circle cx='16' cy='24' r='5'/><path d='M20 28 L48 46'/><path d='M18 30 V44 H12'/><path d='M18 26 V12'/><path d='M8 48 H58'/></symbol>
  <symbol id="pose-dead-bug" viewBox="0 0 64 64"><circle cx='16' cy='38' r='5'/><path d='M21 40 H42'/><path d='M28 40 L26 24'/><path d='M42 40 L46 26'/><path d='M34 40 V52 L28 56'/><path d='M8 52 H58'/></symbol>
  <symbol id="factor-유연성" viewBox="0 0 64 64"><path d='M14 46 Q22 16 34 28 T52 18'/><circle cx='14' cy='46' r='3.5' fill='currentColor' stroke='none'/><circle cx='52' cy='18' r='3.5' fill='currentColor' stroke='none'/></symbol>
  <symbol id="factor-근력" viewBox="0 0 64 64"><path d='M12 40 Q18 24 30 24 Q42 24 46 34'/><path d='M30 24 Q34 12 44 16 Q52 19 50 30 Q48 42 36 44 Q22 46 12 40'/></symbol>
  <symbol id="factor-심폐지구력" viewBox="0 0 64 64"><path d='M32 52 Q10 36 10 24 Q10 14 20 14 Q28 14 32 22 Q36 14 44 14 Q54 14 54 24 Q54 36 32 52'/><path d='M6 30 H20 L25 22 L31 38 L36 30 H58'/></symbol>
  <symbol id="factor-근지구력" viewBox="0 0 64 64"><path d='M14 42 Q20 28 30 28 Q40 28 44 36'/><path d='M30 28 Q34 18 42 21 Q49 24 47 33'/><path d='M50 44 A14 14 0 1 1 44 52'/><path d='M50 38 V45 H43'/></symbol>
</svg>`;

  const FACTOR_NAMES = ["유연성", "근력", "심폐지구력", "근지구력"];

  /* 문서에 한 번만 심는다 */
  function install(){
    if (document.getElementById('moveArtSprite')) return;
    const box = document.createElement('div');
    box.id = 'moveArtSprite';
    box.hidden = true;
    box.innerHTML = SPRITE;
    document.body.appendChild(box);
  }

  /* 자세 그림 한 장. 모르는 id 면 빈 문자열 — 화면이 깨지지 않는다. */
  function pose(id, cls){
    if (!id) return '';
    return `<svg class="${cls || 'move-pose'}" viewBox="0 0 64 64" fill="none"
      stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"
      aria-hidden="true"><use href="#pose-${id}"/></svg>`;
  }

  /* 요인 아이콘 한 장 */
  function factor(name, cls){
    if (!FACTOR_NAMES.includes(name)) return '';
    return `<svg class="${cls || 'move-factor'}" viewBox="0 0 64 64" fill="none"
      stroke="currentColor" stroke-width="3.5" stroke-linecap="round" stroke-linejoin="round"
      role="img" aria-label="${name}"><title>${name}</title><use href="#factor-${name}"/></svg>`;
  }

  return { install, pose, factor, FACTOR_NAMES };
})();

# 3D 동작 구현을 위한 운동 동작 학습 노트

`data/sample/workout_items.json` 의 34개 동작(영상이 없는 기록 종목·고른 종목)을 3D 캐릭터로 보여 주기 위해,
동작마다 **바른 자세·움직임의 범위·박자·흔한 실수**를 공개 자료에서 모았다.
`frontend/js/move-3d.js` 의 자세·손보기(TWEAKS)와 기구(GEAR)는 이 노트를 기준으로 맞춘다.
(검색 정리: 2026-09-12, AI(Claude Code)가 작성)

표기: **시작 자세 → 움직임 → 끝 자세**, 각도는 대략값. 출처는 각 항목 아래.

---

## 맨몸 근력

### squat 스쿼트
- 발은 어깨너비, 발끝은 살짝 바깥. 발 전체(뒤꿈치·엄지·새끼발가락)를 바닥에 붙인다.
- 팔은 앞으로 뻗거나 가슴 앞에 모은다. 가슴은 들고 척추는 중립.
- 엉덩이·무릎·발목을 같이 굽히며 내려간다. **무릎은 발끝 방향을 따라간다**(안으로 모이지 않게).
- 깊이: 엉덩이 주름이 무릎 위보다 낮아지면 평행. 발이 뜨거나 허리가 말리지 않는 깊이까지.
- 박자: 내려가는 데 약 2초, 올라올 때는 조금 빠르게. 몸통 각도는 내내 일정하게(엉덩이만 먼저 솟지 않게).
- 흔한 실수: 무릎 모임, 허리 말림(골반 말림), 상체 과도한 앞기울임.
- 출처: [Healthline](https://www.healthline.com/health/fitness-exercise/proper-squat-form), [Nerd Fitness](https://www.nerdfitness.com/blog/strength-training-101-how-to-squat-properly/), [VASA](https://vasafitness.com/blog/squat-form/)

### pushup 푸시업
- 손은 어깨너비쯤, 엄지가 가슴선(젖꼭지 높이)에 오게. 손을 너무 위(머리 쪽)에 두면 목·어깨에 부담.
- 머리부터 뒤꿈치까지 **한 직선**(움직이는 플랭크). 엉덩이가 처지거나 솟지 않게.
- 팔꿈치는 몸통에서 **약 45°**(위에서 보면 화살표 모양, T 자 아님). 60° 넘게 벌어지면 어깨에 무리.
- 가슴이 바닥에 거의 닿을 때까지 내려간다(바닥 위 10~15cm 에서 멈추면 효과가 줄어든다).
- 박자: 한 회 2초 이상 천천히가 근육 활성이 크고, 빠르면 팔꿈치에 부담.
- 흔한 실수: 팔꿈치 벌어짐, 엉덩이 처짐, 짧은 가동범위.
- 출처: [Built With Science](https://builtwithscience.com/fitness-tips/perfect-push-up-form/), [Peak Endurance PT](https://peakendurancept.com/proper-push-up-form/), [BigBeeFit](https://www.bigbeefit.com/blog/perfect-push-up-form)

### knee-pushup 무릎 푸시업
- 네발 자세에서 시작: 무릎과 발끝이 바닥에 닿고, 손은 어깨보다 살짝 넓게.
- 엉덩이를 내려 **어깨 → 무릎이 한 직선**. 갈비뼈는 내리고 골반은 살짝 말아 코어를 잡는다.
- 정강이는 바닥에 두고 뒤꿈치는 천장 쪽(발을 들어 올리지 않는다).
- 팔꿈치 45° 를 유지하며 가슴이 바닥 가까이 갈 때까지 내려간다. 턱은 살짝 당긴다.
- 흔한 실수: 허리 처짐, 엉덩이 솟음.
- 출처: [NASM](https://www.nasm.org/resource-center/exercise-library/modified-push-up), [ACE](https://www.acefitness.org/resources/everyone/exercise-library/13/bent-knee-push-up/), [MasterClass](https://www.masterclass.com/articles/knee-push-ups-guide)

### lunge 런지
- 한 발을 앞으로 크게 내딛는다. 가장 낮은 자세에서 **양 무릎이 90°**, 앞 무릎은 발목 바로 위(발끝을 넘지 않게), 뒤 무릎은 엉덩이 바로 아래로 내려간다.
- 상체는 곧게 세우고 어깨는 내린다. 앞으로 숙이거나 뒤로 젖히지 않는다.
- 다시 앞발로 밀어 제자리로.
- 흔한 실수: 보폭이 너무 짧거나 길다, 앞 무릎이 앞으로 쏠린다, 상체가 숙여진다, 발 간격이 좁아 균형이 흔들린다.
- 출처: [Cleveland Clinic](https://health.clevelandclinic.org/lunges-muscles-worked), [ClassPass](https://classpass.com/blog/proper-lunge-form-mistakes/), [Anytime Fitness](https://www.anytimefitness.com/blog/proper-lunge-form-to-build-lower-body-strength)

### plank 플랭크
- 팔꿈치는 **어깨 바로 아래**, 아래팔은 나란히, 손은 펴거나 가볍게 주먹.
- 머리부터 뒤꿈치까지 단단한 한 직선. 엉덩이를 조여 골반을 중립으로. 턱을 당기고 바닥을 본다.
- 엉덩이는 처지지도(허리에 부담) 솟지도(쉬워짐) 않게 — 등 윗부분과 비슷한 높이.
- 20~30초부터, 자세가 무너지지 않는 한에서 1분 이상으로.
- 흔한 실수: 엉덩이 처짐(가장 흔함), 엉덩이 솟음, 팔꿈치가 어깨보다 앞.
- 출처: [NASM](https://blog.nasm.org/standard-plank-with-variations), [PureGym](https://www.puregym.com/exercises/abs/planks/), [Daily Burn](https://dailyburn.com/life/fitness/how-to-do-a-plank/)

### crunch 크런치 (싯업과 다르다)
- 누워 무릎을 세우고 발은 바닥. 손은 뒤통수 아래(당기지 않는다)나 가슴 위, 관자놀이.
- **머리와 어깨만** 바닥에서 말아 올린다 — 허리는 바닥에 붙인 채. 상체를 다 세우는 싯업과 달리 가동범위가 작다.
- 턱은 살짝 당긴 채 고정(턱과 가슴 사이 테니스공 하나). 상체는 C 자 곡선.
- 흔한 실수: 손으로 목을 당김, 너무 높이 올라감(허리가 뜸), 등을 젖힘.
- 출처: [Peloton](https://www.onepeloton.com/blog/crunches-vs-sit-ups), [TODAY](https://www.today.com/health/diet-fitness/how-to-do-crunches-rcna202194), [FitCraft](https://getfitcraft.com/exercises/crunches)

### bridge 브리지 (글루트 브리지)
- 누워 무릎을 세운다. 발은 엉덩이 너비, 발끝은 정면, 뒤꿈치는 엉덩이에서 15~20cm(팔을 옆에 뻗었을 때 손끝 바로 너머).
- 뒤꿈치로 바닥을 밀어 **무릎–엉덩이–어깨가 한 직선**이 될 때까지 엉덩이를 든다. 팔은 바닥에 편다.
- 맨 위에서 엉덩이를 1~2초 꽉 조인 뒤 천천히 내린다.
- 흔한 실수: 허리를 과하게 젖힘(갈비뼈 내리고 코어 유지), 발이 너무 멀어 햄스트링만 쓰임, 엉덩이를 조이지 않음.
- 출처: [Outside Run](https://run.outsideonline.com/training/workouts/how-to-perform-a-proper-glute-bridge/), [NASM](https://blog.nasm.org/how-to-do-a-glute-bridge), [Peloton](https://www.onepeloton.com/blog/glute-bridge), [FitCraft](https://getfitcraft.com/exercises/glute-bridges)

### burpee 버피
- 순서: 선 자세(발 엉덩이 너비) → 쪼그려 앉아 손을 바닥에 → 발을 뒤로 점프해 플랭크 → 푸시업 한 번(또는 플랭크 유지) → 발을 손 가까이로 점프 → 팔을 머리 위로 뻗으며 점프.
- 플랭크에서 엉덩이·몸통·무릎이 한 직선. 앞으로 엎드릴 때 등을 굽히지 않는다.
- 발을 손 가까이 충분히 당겨 와야 무릎에 부담이 없다. 무릎은 발끝 방향.
- 점프는 높을 필요가 없다(지구력 운동). 속도보다 자세.
- 흔한 실수: 플랭크에서 엉덩이 처짐, 등 굽음, 발이 손에서 멀리 떨어짐, 코어 풀림.
- 출처: [Peloton](https://www.onepeloton.com/blog/how-to-do-a-burpee), [Healthline](https://www.healthline.com/health/how-to-do-a-burpee), [Spartan](https://www.spartan.com/en/blog/burpee-exercise), [FizzUp](https://blog.fizzup.com/tips-from-the-pros/mistakes-to-avoid-for-the-perfect-burpee/)

## 기구 근력

### bench-press 벤치프레스
- 벤치에 누워 발은 어깨보다 조금 넓게 바닥에 단단히. 엉덩이는 벤치에 붙이고 등 위쪽만 자연스럽게 아치.
- 그립은 어깨보다 조금 넓게 — 바가 가슴에 닿았을 때 아래팔이 수직이 되는 너비.
- 바 경로는 **대각선**: 위에서는 어깨 위, 아래에서는 가슴 아래쪽(명치)에 닿는다.
- 팔꿈치는 몸통에서 **45~60°**(옆으로 90° 벌리면 어깨 충돌). 팔꿈치가 바보다 살짝 앞.
- 흔한 실수: 팔꿈치 벌어짐, 엉덩이 들림, 가슴에서 바를 튕김, 다리 힘을 쓰지 않음.
- 출처: [Barbell Logic](https://barbell-logic.com/how-to-bench-press-setup-safety-bar-path/), [ATHLEAN-X](https://learn.athleanx.com/articles/how-to-bench-press-checklist), [Stronglifts](https://stronglifts.com/bench-press/), [NASM](https://www.nasm.org/resource-center/exercise-library/barbell-bench-press)

### deadlift 데드리프트 (컨벤셔널)
- 바를 **발 가운데(신발끈 위)**에 두고 발은 엉덩이~어깨 너비.
- 엉덩이를 먼저 뒤로 빼 힌지를 만들고, 정강이가 바에 닿을 때까지 무릎을 굽힌다. 등은 평평, 가슴 들고 광배를 조인다.
- 바닥을 밀며 바를 몸에 붙여 올린다. 엉덩이와 어깨가 같이 올라간다(엉덩이만 먼저 솟지 않게).
- 락아웃은 **그냥 똑바로 서는 것** — 엉덩이·무릎을 다 펴고 몸통을 세운다. 뒤로 젖히지 않는다.
- 흔한 실수: 등 말림, 엉덩이 먼저 솟음, 바가 앞으로 떠감, 위에서 허리 과신전.
- 출처: [BarBend](https://barbend.com/deadlift-mistakes/), [Booty Builder](https://bootybuilder.com/exercises/deadlift/proper-form-technique/), [Dynamic PT](https://dynamic-pt.com/deadlift-form-common-mistakes-and-safety-considerations/)

### barbell-squat 바벨 스쿼트 (백 스쿼트)
- 하이바: 견갑을 모아 만든 승모근 위 선반에 바를 얹는다. 로우바: 견갑극 바로 아래. 목뼈 위에 얹으면 안 된다.
- 그립은 어깨보다 넓게, 손은 편한 범위에서 좁게. 팔꿈치는 아래·뒤로.
- 발은 어깨너비, 발끝은 정면~10° 바깥. 체중은 발 가운데.
- 깊이는 허벅지가 바닥과 평행 이하. 무릎은 발끝을 따라가고 뒤꿈치는 떨어지지 않는다.
- 흔한 실수: 무릎 모임, 뒤꿈치 들림(발목 가동성), 바를 목에 얹음.
- 출처: [BuiltLean](https://www.builtlean.com/back-squat-form/), [Squat University](https://squatuniversity.com/2016/03/18/how-to-perfect-the-high-bar-back-squat-2/), [BarBend](https://barbend.com/high-bar-versus-low-bar-squats/), [Barbell Medicine](https://www.barbellmedicine.com/blog/how-to-squat/)

### lat-pulldown 랫풀다운
- 그립은 어깨의 약 1.5배 너비, 오버핸드. 허벅지 패드를 맞춰 앉는다.
- 가슴을 들고 **10~15° 정도만** 뒤로 기댄다. 견갑을 먼저 내리고(어깨를 귀에서 멀리) 팔꿈치를 엉덩이 쪽으로 곧장 내린다.
- 바는 **가슴 윗부분**까지. 목이나 뒤통수로 당기지 않는다. 올릴 때는 팔이 완전히 펴져 광배가 늘어날 때까지 천천히.
- 흔한 실수: 몸을 뒤로 흔들며 당김(로우가 됨), 너무 좁은 그립(전완 위주), 너무 무거운 중량.
- 출처: [Fringe Sport](https://www.fringesport.com/blogs/news/how-to-lat-pulldown-proper-form-grip-variations-common-mistakes), [StrengthLog](https://www.strengthlog.com/lat-pulldown-with-pronated-grip/), [PowerliftingTechnique](https://powerliftingtechnique.com/lat-pulldowns/)

### leg-press 레그프레스
- 발은 어깨너비로 발판 가운데(낮게 두면 허벅지 앞, 높게 두면 엉덩이·햄스트링).
- 등과 머리를 패드에 붙이고 손잡이를 잡는다.
- 무릎이 **약 90°** 가 될 때까지 내린다. 골반이 패드에서 말려 올라오기 전에 멈춘다.
- 무릎을 다 잠그지 않는 지점까지 민다. 무릎은 발끝 방향.
- 흔한 실수: 허리 아치·엉덩이 들림, 무릎 잠금, 무릎 모임, 반만 내리기.
- 출처: [Select Fitness](https://selectfitness.com/blogs/leg-press-machines/how-to-use-the-leg-press-machine), [Powertec](https://powertec.com/blogs/power-up-blog/technique-mastery-how-to-perform-a-leg-press-properly), [RitFit](https://www.ritfitsports.com/blogs/article/how-to-do-leg-press)

### dumbbell-curl 덤벨 컬
- 발 어깨너비, 팔은 옆으로 완전히 편 채 손바닥 앞(수피네이션).
- **팔꿈치를 옆구리에 고정**하고 위팔은 움직이지 않는다. 아래팔만 올려 덤벨을 어깨 높이까지, 이두를 완전히 수축.
- 다 편 상태까지 천천히 내린다. 손목은 중립(꺾지 않기).
- 흔한 실수: 팔꿈치가 앞으로 나감, 몸을 흔들어 반동, 가동범위 부족, 손목 꺾음.
- 출처: [Fitbod](https://fitbod.me/blog/how-to-do-bicep-curls/), [ATHLEAN-X](https://learn.athleanx.com/articles/how-to-do-bicep-curls), [RitFit](https://www.ritfitsports.com/blogs/article/how-to-do-dumbbell-bicep-curls)

### shoulder-press 숄더프레스 (덤벨)
- 덤벨을 어깨 높이에 든다. 손바닥은 **앞 또는 서로 마주보게(머리 쪽)**. 아래팔은 수직, 손목은 아래팔 위에 쌓는다.
- 팔꿈치는 옆으로 다 벌리지 않고 **살짝 앞(약 45°)**, 덤벨 바로 아래.
- 어깨 관절 위로 곧장 밀어 팔꿈치를 편다(락아웃). 위에서 덤벨을 부딪히지 않는다.
- 갈비뼈를 내리고 허리는 중립 — 뒤로 기대면 인클라인 프레스가 된다.
- 흔한 실수: 팔을 다 펴지 않음, 앞이나 뒤로 밀어 균형 잃음, 허리 과신전, 팔꿈치 벌어짐.
- 출처: [Garage Gym Reviews](https://www.garagegymreviews.com/dumbbell-shoulder-press), [Stronglifts](https://stronglifts.com/overhead-press/), [ISSA](https://www.issaonline.com/blog/post/overhead-press-proper-form-variations-and-common-mistakes)

### kettlebell-swing 케틀벨 스윙
- **힙 힌지**이지 스쿼트가 아니다: 무릎은 조금만 굽히고 엉덩이를 뒤로 뺀다.
- 케틀벨이 다리 사이로 들어왔다가, 엉덩이를 앞으로 **스냅**하며 펴는 힘으로 앞으로 나간다.
- 팔은 힘을 빼고 길게 — 엉덩이 힘을 전달하는 끈. 팔로 들지 않는다.
- 가슴 높이에서 잠시 무중력이 되고 다시 내려온다. 몸통은 서는 순간 완전히 펴진다.
- 흔한 실수: 무릎을 너무 굽힘(스쿼트), 팔로 들어 올림, 너무 낮게 스윙.
- 출처: [ISSA](https://www.issaonline.com/blogs/strength/kettlebell-swings-muscles-worked-proper-form-and-more), [Greatist](https://greatist.com/move/how-to-do-the-perfect-kettlebell-swing), [Chuze](https://chuzefitness.com/blog/how-to-do-kettlebell-swings/), [Kettlebells Workouts](https://kettlebellsworkouts.com/teaching-points-for-the-kettlebell-swing/)

## 유산소

### jump-rope 줄넘기
- 팔꿈치는 옆구리에 붙이고 아래팔은 살짝 바깥. 줄은 **손목의 작은 회전**으로 돌린다(팔 전체 아님). 그립은 힘 빼고.
- 점프는 낮게 — 바닥에서 **2~5cm**. 발볼로 가볍게 착지하고 무릎은 항상 살짝 굽힌다.
- 흔한 실수: 팔 전체로 돌림, 너무 높이 뜀, 뒤꿈치 착지.
- 출처: [Elevate Rope](https://www.elevaterope.com/blogs/articles/jump-rope-techniques/), [Crossrope](https://www.crossrope.com/blogs/blog/how-to-jump-rope/), [MasterClass](https://www.masterclass.com/articles/jump-rope-workout-guide), [Buddy Lee](https://buddyleejumpropes.com/blogs/jump-rope-training/how-to-jump-rope)

### stair 계단 오르기
- 엉덩이에서 살짝 앞으로 기울인다(가슴이 무릎보다 조금 앞). 이러면 엉덩이 근육이 밀어 올린다.
- **발 전체**를 계단에 올리고 뒤꿈치까지 써서 민다. 발끝으로만 밀지 않는다.
- 엉덩이–무릎–발끝이 한 줄. 정강이는 되도록 수직에 가깝게.
- 출처: [Heart + Bones Yoga](https://heartandbonesyoga.com/resources/how-climb-stairs-without-knee-pain/), [Butheau Physio](https://www.butheauphysio.com/blog/how-to-climb-stairs-correctly-to-prevent-knee-pain/), [Wright PT](https://wrightpt.com/reduce-knee-pain-during-stair-climbing/), [Pilates Encyclopedia](https://www.pilatesencyclopedia.com/blog/climb-stairs-without-knee-pain)

### run 러닝
- 상체는 곧게, 어깨는 귀 아래, 발목에서부터 살짝 앞으로 기운다(허리를 굽히는 게 아님).
- 팔꿈치 **약 90°**, 팔은 앞뒤로 흔들고 몸 앞에서 교차하지 않는다. 어깨는 힘 빼기.
- 케이던스 분당 170~180보, 짧고 빠른 걸음. 발은 몸 아래 **미드풋**으로 착지.
- 출처: [Brooks](https://www.brooksrunning.com/en_it/blog/training-workouts/tips-for-proper-running-form.html), [ASICS](https://www.asics.com/gb/en-gb/asics-advice/correct-running-form/), [Marathon Handbook](https://marathonhandbook.com/proper-running-form/), [Road Runner Sports](https://www.roadrunnersports.com/blog/proper-running-form/)

### walk 걷기
- 머리를 들고 시선은 수평선, 어깨는 뒤로 내려 힘 빼고, 척추를 길게.
- 팔은 어깨에서부터 시계추처럼 앞뒤로. 운동 걷기는 팔꿈치 90°로 접어 빠르게.
- **뒤꿈치 착지 → 발 가운데 → 발끝으로 밀기**. 보폭은 짧고 빠르게(오버스트라이드 금지).
- 출처: [Harvard Health](https://www.health.harvard.edu/healthy-aging-and-longevity/perfecting-your-walking-technique), [Garage Gym Reviews](https://www.garagegymreviews.com/walking-technique), [Healthline](https://www.healthline.com/health/how-to-walk)

### treadmill 러닝머신
- **손잡이를 잡지 않는다**(자세가 무너지고 운동량이 줄어든다). 상체는 곧게, 턱은 수평, 시선은 앞.
- 팔은 자연스럽게 흔든다. 미드풋 착지 후 발끝으로 민다. 발을 너무 높이 들지 않는다.
- 출처: [treadmill.run](https://www.treadmill.run/how-to-use-proper-form-on-a-treadmill/), [YMCA](https://www.ymcastark.org/blog/why-holding-treadmill-can-hurt-your-workout), [Bustle](https://www.bustle.com/wellness/how-to-walk-on-treadmill-incline)

### cycle 실내 자전거
- 안장 높이: 페달이 맨 아래일 때 무릎이 **25~35° 정도만** 굽는 높이(선 채로 고관절 높이). 3시 방향에서 무릎이 페달 축 위.
- 엉덩이에서 힌지해 상체를 살짝 앞으로, 가슴은 들고 어깨는 내리고 팔꿈치는 부드럽게. 척추 중립, 엉덩이가 좌우로 흔들리지 않게.
- 항상 약간의 저항을 둔다(없으면 안장에서 튄다).
- 흔한 실수: 안장이 너무 낮음(무릎 압박) 또는 높음(엉덩이 흔들림), 저항 0.
- 출처: [Aaptiv](https://aaptiv.com/magazine/perfect-indoor-cycling-form/), [AFAA](https://blog.afaa.com/indoor-cycling-form), [UPMC](https://www.upmcmyhealthmatters.com/indoor-cycling-proper-form/)

### rowing 로잉머신
- **캐치**: 정강이 수직, 팔은 편 채, 상체는 살짝 앞(어깨가 엉덩이보다 앞).
- **드라이브**: 다리로 먼저 밀고 → 엉덩이로 상체를 연 뒤 → 마지막에 팔로 손잡이를 갈비뼈 아래로 당긴다. 힘의 약 60%가 다리.
- **피니시**: 수직에서 25~30° 뒤로 기대고 손잡이는 갈비뼈, 팔꿈치는 몸 옆을 지난다.
- **리커버리**: 팔 → 상체 → 다리 순서로 되돌린다. 드라이브:리커버리 = 1:2 로 천천히.
- 흔한 실수: 등 말림, 팔로 먼저 당김, 과하게 앞으로 뻗음, 리커버리를 서두름, 무릎을 먼저 굽혀 손잡이가 무릎에 걸림, 손잡이를 꽉 쥠.
- 출처: [Life Fitness](https://www.lifefitness.com/en-us/blog/understanding-the-basics-of-rowing-technique-1061964), [Ergatta](https://ergatta.com/blogs/indoor-rowing-beginner/rowing-form-beginner-guide), [Concept2](https://www.concept2.com/training/improve-your-rowing-technique), [Hydrow](https://hydrow.com/blog/rowing-machine-setup-mistakes/), [British Rowing](https://plus.britishrowing.org/2022/10/24/common-errors-and-how-to-correct-them/)

### swim 수영 (자유형)
- 몸은 수면에 수평하게 길게(어뢰처럼). 엉덩이·몸통·어깨가 **한 덩어리로 좌우 롤링**하며 팔을 젓는다.
- 팔은 번갈아: 물속에서 캐치 → 풀 → 물 밖으로 리커버리. 다리는 엉덩이에서 시작하는 작은 플러터 킥을 계속.
- 호흡은 롤링에 맞춰 머리를 옆으로 돌려(한쪽 고글은 물속에 둔 채).
- 출처: [U.S. Masters Swimming](https://www.usms.org/fitness-and-training/guides/freestyle/body-position), [TritonWear](https://www.tritonwear.com/mastering-your-freestyle-swimming-technique), [MySwimPro](https://blog.myswimpro.com/2023/02/01/try-these-drills-to-fix-your-freestyle-rotation/), [Effortless Swimming](https://effortlessswimming.com/swimming-technique/)

## 스트레칭·호흡·균형

### hamstring-stretch 햄스트링 스트레칭 (선 자세)
- 한 발을 앞에 두고 뒤꿈치를 바닥에, 발끝은 위로. 앞 다리는 편다. 뒷무릎은 살짝 굽힌다.
- 엉덩이를 뒤로 빼며 **등을 평평하게 유지한 채** 힌지해 앞으로 숙인다. 손은 앞 다리를 따라 내린다.
- 다리 뒤쪽이 당기는 지점에서 15~30초, 반대쪽.
- 흔한 실수: 등을 둥글게 말아 숙임.
- 출처: [Popular Science](https://www.popsci.com/health/hamstring-stretches-physical-therapist/), [Hinge Health](https://www.hingehealth.com/resources/articles/hamstring-stretch/), [Mayo Clinic](https://www.mayoclinic.org/healthy-lifestyle/fitness/in-depth/stretching/art-20546848)

### calf-stretch 종아리 스트레칭 (벽)
- 벽을 마주 보고 팔 길이만큼 떨어져 손바닥을 어깨 높이에 댄다.
- 한 발을 60~90cm 뒤로. **뒷다리는 곧게, 뒤꿈치는 바닥에**, 발끝은 정면. 앞 무릎은 굽힌다.
- 벽을 밀며 몸을 앞으로 기울여 뒷종아리가 당길 때 20~30초. 반대쪽.
- 출처: [Illinois Extension](https://eat-move-save.extension.illinois.edu/move/exercise/wall-calf-stretch), [Rehab Hero](https://www.rehabhero.ca/exercise/wall-calf-stretch), [BetterMe](https://betterme.world/articles/wall-calf-stretch-exercise/)

### shoulder-stretch 어깨 스트레칭 (크로스 바디)
- 한 팔을 **어깨 높이로 곧게** 가슴 앞을 가로지른다. 반대 손으로 팔꿈치 위쪽을 가슴 쪽으로 가볍게 당긴다.
- 어깨는 내리고(귀 쪽으로 올리지 않기), 몸통은 돌리지 않는다. 15~30초, 반대쪽.
- 출처: [Fitbod](https://fitbod.me/exercises/cross-body-arm-stretch), [Endomondo](https://www.endomondo.com/exercise/cross-body-shoulder-stretch), [Muscle MX](https://www.musclemx.com/blogs/blog/how-to-do-the-cross-body-shoulder-stretch-a-physical-therapists-guide)

### hip-stretch 고관절 스트레칭 (반무릎 고관절 굴곡근)
- 반무릎(90/90): 뒷무릎은 엉덩이 바로 아래, 앞발은 앞무릎 아래. 상체는 곧게.
- **골반을 뒤로 말고(꼬리뼈를 아래로) 뒷다리 쪽 엉덩이를 조인 뒤**, 몸을 2~3cm 앞으로 옮긴다. 뒷다리 고관절 앞이 당긴다.
- 30~45초, 반대쪽.
- 흔한 실수: 허리를 젖혀 앞으로 밀기(굴곡근은 안 늘어나고 허리만 눌린다).
- 출처: [FMS](https://www.functionalmovement.com/Exercises/788/half_kneeling_hip_flexor_stretch), [FitCraft](https://getfitcraft.com/exercises/half-kneeling-stretch), [Limitless PT](https://limitlesspts.com/hip-flexor-stretches/)

### twist 누워 허리 비틀기 (수파인 트위스트)
- 누워 팔을 어깨 높이로 T 자로 벌린다.
- 한 무릎을 굽혀 반대쪽으로 넘겨 바닥 쪽으로 내린다. **양 어깨는 바닥에 붙인 채**. 반대 손을 무릎에 얹고 머리는 반대쪽을 본다.
- 무릎이 바닥에 닿을 필요는 없다. 20~30초, 반대쪽.
- 출처: [TODAY](https://www.today.com/health/diet-fitness/supine-spinal-twist-rcna148101), [Your House Fitness](https://www.yourhousefitness.com/blog/exercise-tutorial-supine-twist), [Yoga Basics](https://www.yogabasics.com/asana/knee-down-twist/), [Athletico](https://www.athletico.com/2015/03/24/supine-twist/)

### neck-stretch 목 스트레칭 (옆)
- 앉거나 서서 어깨를 내린다. 귀를 같은 쪽 어깨로 기울인다. 반대 어깨는 내려 둔다.
- 손은 머리 옆에 얹어 무게만 살짝 더한다 — **누르지 않는다**. 20~30초, 반대쪽.
- 출처: [Niel Asher](https://nielasher.com/blogs/strength-and-conditioning/assisted-lateral-neck-stretch), [ACE](https://www.acefitness.org/resources/everyone/exercise-library/202/lateral-neck-flexion/), [Healthline](https://www.healthline.com/health/neck-flexion), [Dani Winks](https://www.daniwinksflexibility.com/flexopedia/ear-to-shoulder-stretch)

### deep-breath 복식 호흡
- 누워 무릎을 세우거나(처음) 의자에 앉는다. 한 손은 가슴, 한 손은 배.
- 코로 천천히 들이마시며 **배가 부풀고 가슴 손은 움직이지 않게**. 입술을 오므려 천천히 내쉬며 배가 꺼지고 복근이 가볍게 조인다.
- 한 번에 약 10분, 하루 3~4회.
- 출처: [Cleveland Clinic](https://my.clevelandclinic.org/health/articles/9445-diaphragmatic-breathing), [Healthline](https://www.healthline.com/health/diaphragmatic-breathing), [Kaiser Permanente](https://healthy.kaiserpermanente.org/health-wellness/health-encyclopedia/he.belly-breathing-diaphragmatic-breathing.aa141579), [Physiopedia](https://www.physio-pedia.com/Diaphragmatic_Breathing_Exercises)

### one-leg 한 발 서기
- 곧게 서서 발을 모으고 손은 허리(또는 의자·벽 옆에서). 시선은 앞, 가슴은 들고.
- 한 발로 체중을 옮기고 반대 발을 바닥에서 든다(무릎 살짝 굽힘). 딛는 무릎은 잠그지 않는다.
- 5~10초부터 시작해 30초, 나중엔 60초까지.
- 출처: [More Life Health](https://morelifehealth.com/single-leg-stance), [Mayo Clinic](https://www.mayoclinic.org/healthy-lifestyle/fitness/in-depth/balance-exercises/art-20546836), [GoodRx](https://www.goodrx.com/health-topic/senior-health/balance-exercises-for-seniors), [Active Silvers](https://activesilvers.com/safe-single-leg-balance-exercises-for-older-adults/)

### side-plank 사이드 플랭크
- 옆으로 누워 아래팔을 바닥에, **팔꿈치는 어깨 바로 아래**. 발은 포개거나(쉽게는) 앞뒤로 엇갈리게.
- 엉덩이를 들어 머리부터 발까지 한 직선. 엉덩이는 정면을 향한 채 처지거나 돌아가지 않게. 윗손은 허리나 천장.
- 머리는 척추와 일직선, 숨은 계속 쉰다.
- 흔한 실수: 엉덩이 처짐, 팔꿈치가 어깨 아래를 벗어남, 엉덩이 회전, 머리 떨굼, 숨 참기.
- 출처: [NASM](https://www.nasm.org/resource-center/exercise-library/side-plank), [ATHLEAN-X](https://learn.athleanx.com/articles/abs-for-men/how-to-do-side-planks), [Garage Gym Reviews](https://www.garagegymreviews.com/side-plank), [Peloton](https://www.onepeloton.com/blog/side-planks)

### dead-bug 데드버그
- 누워 팔을 천장으로 곧게 뻗고, 엉덩이와 무릎을 **90°** 로 든다. 허리를 바닥에 붙이고 갈비뼈를 내린다.
- 한 팔을 머리 위로, **반대쪽 다리**를 앞으로 천천히 뻗는다(뒤꿈치는 바닥 쪽). 허리가 뜨기 전에 멈추고 1~2초 유지, 내쉬며 돌아온다. 반대쪽.
- 흔한 실수: 허리 아치, 갈비뼈 들림, 빠르게 휘두르기.
- 출처: [NASM](https://www.nasm.org/resource-center/exercise-library/dead-bug), [Nike](https://www.nike.com/a/perfect-deadbug-form), [Planfit](https://planfit.ai/en/exercise/dead-bug), [Yorkville Sports Medicine](https://www.yorkvillesportsmed.com/blog/the-dead-bug-exercise-and-how-you-can-do-it-perfectly)

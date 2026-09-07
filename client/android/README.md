# BIDAR Android

BID + RADAR — 공고/문서를 선택해 챗봇에게 질의응답할 수 있는 Android 클라이언트입니다.

## 주요 화면

| 화면 | 설명 |
| --- | --- |
| Splash | 앱 진입 화면. 이후 Home으로 이동하며 백스택에서 제거됨 |
| Home | 문서(공고) 목록 조회, 최근 대화 이력 표시, Chat/Setting으로 이동 |
| Chat | 특정 문서(`documentId`)에 대한 챗봇 대화 화면. 페이징 기반 채팅 리스트, SSE 스트리밍 답변 지원 |
| Setting | 스트리밍(SSE) 모드/OpenAI 모드 토글, 전체 채팅 기록 삭제 |

화면 이동은 `app/navigation/BidarNavHost.kt`, `Route.kt`에 정의되어 있습니다.

## 아키텍처

Clean Architecture 스타일로 `app` / `data` / `domain` 3개 레이어로 구성됩니다.

```
com.yuventius.bidar
├── app
│   ├── core          # Application, MainActivity
│   ├── di            # Hilt 모듈 (Network, Database, Repository, CoroutineScope)
│   ├── navigation     # NavHost, Route 정의
│   ├── ui
│   │   ├── theme      # Compose 테마/컬러/타이포그래피
│   │   └── view
│   │       ├── common/component  # 공용 컴포저블 (채팅 말풍선, 날짜 구분선, 설정 카드 등)
│   │       └── screen            # 화면별 View/ViewModel/State (splash, home, chat, setting)
│   └── util           # 날짜 포맷 등 확장 함수
├── data
│   ├── local          # Room (AppDatabase, ChatDao, Entity)
│   └── remote         # Retrofit API, SSE 클라이언트, Repository 구현체
└── domain
    ├── model          # Chat, Document, ChatSender 등 도메인 모델
    ├── repository     # Repository 인터페이스
    └── util           # 공통 유틸
```

- **UI**: Jetpack Compose + Material3, Navigation Compose
- **상태 관리**: [Orbit MVI](https://orbit-mvi.org/) (`OrbitContainerHost`, `intent`/`reduce`, SideEffect)
- **DI**: Hilt
- **네트워크**: Retrofit + kotlinx.serialization + OkHttp (SSE는 `okhttp-sse` 사용)
- **로컬 저장소**: Room (+ Paging 3, `PagingSource` 기반 채팅 목록)
- **비동기**: Kotlin Coroutines / Flow

## 채팅(Chat) 동작 방식

- 채팅 목록은 Room + Paging 3로 관리되며(`ChatDao.getChats`), `ChatVM`에서 날짜별 구분선(`ChatListItem.DateSeparator`)을 삽입해 보여줍니다.
- 문서별 첫 진입 시 대화 기록이 없으면 웰컴 메시지를 자동 삽입합니다(`ChatVM.ensureWelcomeMessage`).
- 메시지 전송/응답 처리는 화면(ViewModel) 생명주기와 무관하게 Repository 레벨에서 진행되어, 화면을 나갔다 재진입해도 응답 대기 상태(`isWaitingForResponse`)와 스트리밍 중간 결과(`streamingAnswer`)를 그대로 이어서 관찰할 수 있습니다.
- 두 가지 응답 모드를 Setting 화면에서 토글할 수 있습니다.
  - **일반 모드**: `ChatApi.postChat` (Retrofit suspend 호출, `/chat`)
  - **SSE 스트리밍 모드**: `ChatSseClient`가 OkHttp `EventSource`로 `/chat?use_streaming=true`를 직접 구독해 토큰 단위로 흘려보냄
  - **OpenAI 모드**: `use_open_ai` 쿼리 파라미터로 백엔드에 전달
- API 요청은 JSON 바디가 아닌 쿼리 파라미터 방식입니다(백엔드 FastAPI 시그니처에 맞춤).

## 네트워크 설정

- Base URL: `app/di/NetworkModule.kt`의 `BASE_URL` 상수
- 챗봇 응답 생성이 최대 2분 30초까지 걸리는 것이 관측되어 OkHttp `readTimeout`을 3분으로 설정
- `usesCleartextTraffic="true"`로 HTTP 평문 통신 허용 (개발/테스트용 백엔드 주소)

## 빌드 & 실행

### 요구 사항

- Android Studio (AGP `9.2.1` 대응 버전 이상)
- JDK 21
- minSdk 30 / targetSdk·compileSdk 37

### 빌드

```bash
# 프로젝트 루트(client/android)에서
./gradlew assembleDebug   # 또는 gradlew.bat assembleDebug (Windows)
```

### 실행

Android Studio에서 `client/android` 디렉터리를 프로젝트로 열고 `app` 모듈을 에뮬레이터/실기기에서 Run 하면 됩니다.

### 테스트

```bash
./gradlew testDebugUnitTest        # 단위 테스트
./gradlew connectedDebugAndroidTest # 계측(UI) 테스트
```

## 기술 스택 요약

| 영역 | 라이브러리 |
| --- | --- |
| UI | Jetpack Compose, Material3, Navigation Compose |
| 상태관리 | Orbit MVI |
| DI | Hilt |
| 네트워크 | Retrofit, OkHttp, OkHttp-SSE, kotlinx.serialization |
| 로컬 DB | Room, Room-Paging |
| 페이징 | Paging 3 (Compose 확장 포함) |
| 로깅 | orhanobut/logger |

버전 상세는 `gradle/libs.versions.toml`을 참고하세요.

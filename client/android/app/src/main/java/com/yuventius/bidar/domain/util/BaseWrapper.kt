package com.yuventius.bidar.domain.util

/**
 * BIDAR
 * Class: BaseWrapper
 * Created by Ven Choi on 2026-09-01
 *
 * Domain <-> Data 모델 변환을 담당하는 베이스 클래스.
 * toDomain() / toData()를 멤버 확장 함수로 선언해두면, object로 구현한 하위 Wrapper에서
 * 오버라이드한 확장 함수를 다음과 같이 import해서 일반 확장 함수처럼 사용할 수 있다.
 *
 * import com.yuventius.bidar.data.remote.model.DocumentWrapper.toData
 * import com.yuventius.bidar.data.remote.model.DocumentWrapper.toDomain
 *
 * document.toData()
 * documentRemote.toDomain()
 */
abstract class BaseWrapper<Domain, Data> {
    abstract fun Domain.toData(): Data
    abstract fun Data.toDomain(): Domain
}
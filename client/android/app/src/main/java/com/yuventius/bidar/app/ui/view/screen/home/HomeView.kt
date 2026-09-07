package com.yuventius.bidar.app.ui.view.screen.home

import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.State
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.ColorFilter
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.hilt.lifecycle.viewmodel.compose.hiltViewModel
import com.yuventius.bidar.R
import com.yuventius.bidar.app.ui.theme.MidnightIndigo
import com.yuventius.bidar.app.ui.theme.MidnightIndigo60
import com.yuventius.bidar.app.ui.theme.SoftGray
import com.yuventius.bidar.app.ui.view.common.component.DocumentCardView
import com.yuventius.bidar.app.ui.view.screen.home.state.HomeState
import com.yuventius.bidar.app.ui.view.screen.home.state.HomeStatus
import com.yuventius.bidar.app.util.noRippleClickable
import com.yuventius.bidar.domain.model.Document
import org.orbitmvi.orbit.compose.collectAsState
import org.orbitmvi.orbit.compose.collectSideEffect

/**
 * BIDAR
 * Class: HomeView
 * Created by Ven Choi on 2026-09-01
 */
@Composable
fun HomeView (
    modifier: Modifier = Modifier,
    vm: HomeVM = hiltViewModel(),
    onNavigateToChat: (String) -> Unit = {},
    onNavigateToSetting: () -> Unit = {}
) {
    vm.collectSideEffect {

    }

    val state by vm.collectAsState()

    HomeContent (
        modifier = modifier
            .padding(horizontal = 18.dp),
        state = state,
        onNavigateToChat = onNavigateToChat,
        onNavigateToSetting = onNavigateToSetting,
        onRefresh = {
            vm.refreshDocuments()
        }
    )
}

@Composable
fun HomeContent (
    modifier: Modifier = Modifier,
    state: HomeState = HomeState(),
    onNavigateToChat: (String) -> Unit = {},
    onNavigateToSetting: () -> Unit = {},
    onRefresh: () -> Unit = {}
) {
    Column (
        modifier = modifier
            .padding(top = 13.dp),
        verticalArrangement = Arrangement.spacedBy(24.dp)
    ) {
        Row (
            modifier = Modifier
                .fillMaxWidth(),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Image (
                painter = painterResource(R.drawable.ic_logo_filled),
                contentDescription = null
            )
            Spacer(modifier = Modifier.weight(1F))
            Image (
                modifier = Modifier
                    .size(25.dp)
                    .noRippleClickable {
                        onNavigateToSetting.invoke()
                    },
                painter = painterResource(R.drawable.ic_setting),
                contentDescription = null,
                colorFilter = ColorFilter.tint(MidnightIndigo)
            )
        }
        Column (
            verticalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            Text (
                text = "안녕하세요!",
                fontWeight = FontWeight.Medium,
                fontSize = 24.sp
            )
            Text (
                text = "문서를 선택하여 대화를 시작해보세요.",
                fontWeight = FontWeight.Medium,
                fontSize = 18.sp
            )
        }
        Column (
            modifier = Modifier
                .fillMaxWidth(),
            verticalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            Row (
                modifier = Modifier
                    .fillMaxWidth(),
                verticalAlignment = Alignment.CenterVertically
            ) {
                Spacer(modifier = Modifier.weight(1F))
                Row (
                    modifier = Modifier
                        .noRippleClickable {
                            onRefresh.invoke()
                        },
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Image (
                        modifier = Modifier
                            .size(20.dp),
                        painter = painterResource(R.drawable.ic_refresh),
                        contentDescription = null,
                        colorFilter = ColorFilter.tint(Color.LightGray)
                    )
                    Text (
                        text = "새로고침",
                        fontSize = 12.sp,
                        color = Color.LightGray
                    )
                }
            }

            if (state.status == HomeStatus.LOADING) {
                Box (
                    modifier = Modifier
                        .fillMaxSize(),
                    contentAlignment = Alignment.Center
                ) {
                    CircularProgressIndicator (
                        color = MidnightIndigo
                    )
                }
            } else {
                LazyColumn (
                    modifier = Modifier
                        .fillMaxWidth(),
                    verticalArrangement = Arrangement.spacedBy(8.dp)
                ) {
                    items(state.documents) { document: Document ->
                        DocumentCardView (
                            modifier = Modifier
                                .fillMaxWidth(),
                            document = document
                        ) {
                            onNavigateToChat.invoke(document.documentId)
                        }
                    }
                }
            }
        }
    }
}

@Preview
@Composable
fun HomeViewPreview() {
    HomeContent()
}
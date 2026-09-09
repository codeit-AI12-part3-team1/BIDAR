package com.yuventius.bidar.app.ui.view.screen.setting

import android.content.Context
import android.widget.Toast
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.BasicAlertDialog
import androidx.compose.material3.Card
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.window.DialogProperties
import androidx.hilt.lifecycle.viewmodel.compose.hiltViewModel
import com.yuventius.bidar.app.ui.theme.MidnightIndigo
import com.yuventius.bidar.app.ui.view.common.component.ConfigCardView
import com.yuventius.bidar.app.ui.view.common.component.ConfigToggleView
import com.yuventius.bidar.app.ui.view.common.component.NavHeader

/**
 * BIDAR
 * Class: SettingView
 * Created by Ven Choi on 2026-09-07
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun SettingView (
    modifier: Modifier = Modifier,
    vm: SettingVM = hiltViewModel(),
    context: Context = LocalContext.current,
    onBack: () -> Unit = {}
) {
    val showDialog = remember { mutableStateOf(false) }
    val useStreaming by vm.useStreaming.collectAsState()
    val useOpenAi by vm.useOpenAi.collectAsState()

    Column (
        modifier = modifier,
        verticalArrangement = Arrangement.spacedBy(12.dp)
    ) {
        NavHeader (
            modifier = Modifier
                .fillMaxWidth(),
            title = "Setting"
        ) { onBack.invoke() }
        ConfigCardView (
            modifier = Modifier
                .padding(horizontal = 12.dp),
            configTitle = "채팅 기록 초기화"
        ) { showDialog.value = true }
        ConfigToggleView (
            modifier = Modifier
                .padding(horizontal = 12.dp),
            configTitle = "SSE 모드 활성화",
            checked = useStreaming,
            onCheckedChange = vm::setUseStreaming
        )
        ConfigToggleView (
            modifier = Modifier
                .padding(horizontal = 12.dp),
            configTitle = "LLM을 Open AI로 변경",
            checked = useOpenAi,
            onCheckedChange = vm::setUseOpenAi
        )

        if (showDialog.value) {
            BasicAlertDialog (
                onDismissRequest = {
                    showDialog.value = false
                },
                properties = DialogProperties()) {
                Card (
                    modifier = Modifier
                        .fillMaxWidth(),
                    shape = RoundedCornerShape(16.dp)
                ) {
                    Column (
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(14.dp),
                        horizontalAlignment = Alignment.CenterHorizontally,
                        verticalArrangement = Arrangement.spacedBy(12.dp)
                    ) {
                        Text (
                            text = "모든 채팅 기록을 초기화 하시겠습니까?",
                            fontWeight = FontWeight.Bold,
                            fontSize = 20.sp
                        )

                        Row (
                            modifier = Modifier
                                .fillMaxWidth(),
                        ) {
                            Spacer(modifier = Modifier.weight(1F))
                            TextButton (
                                onClick = {
                                    vm.clearAllChats()
                                    showDialog.value = false
                                    Toast.makeText(context, "모든 채팅이 삭제되었습니다.", Toast.LENGTH_SHORT).show()
                                }
                            ) {
                                Text (
                                    text = "삭제",
                                    color = Color.Red
                                )
                            }
                            TextButton (
                                onClick = {
                                    showDialog.value = false
                                }
                            ) {
                                Text (
                                    text = "취소",
                                    color = MidnightIndigo
                                )
                            }
                        }
                    }
                }
            }
        }
    }
}
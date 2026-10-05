#include "stm32f10x.h"
#include "Serial.h"
#include <string.h>

#define COMMAND_BUFFER_SIZE 16
#define PAN_CENTER_US 1500U
#define PAN_STEP_US 50U
#define PAN_TEST_STEP_US 100U
#define PAN_WIDE_STEP_US 150U
#define PAN_FAR_STEP_US 200U
#define PAN_NEXT_STEP_US 250U
#define PAN_FURTHER_STEP_US 300U
#define PAN_MORE_STEP_US 350U
#define PAN_MORE2_STEP_US 400U
#define PAN_NEAR_EDGE_STEP_US 450U
#define PAN_EDGE_STEP_US 500U
#define PAN_PERIOD_US 20000U
#define PAN_TIMEOUT_MS 2000U
#define PAN_PROBE_MS 60U
#define TRACK_PAN_MIN_US 500U
#define TRACK_PAN_MAX_US 2500U
#define TRACK_TILT_MIN_US 750U
#define TRACK_TILT_MAX_US 2250U
#define TRACK_TARGET_STEP_US 80U
#define TRACK_RAMP_STEP_US 24U
#define TRACK_RAMP_PERIOD_MS 20U

static char CommandBuffer[COMMAND_BUFFER_SIZE];
static uint8_t CommandLength;
static volatile uint32_t PanMilliseconds;
static uint32_t PanDeadline;
static uint16_t PanPulseUs;
static uint8_t PanReady;
static uint8_t PanActive;
static uint8_t PanCentered;
static uint32_t TiltDeadline;
static uint16_t TiltPulseUs;
static uint8_t TiltReady;
static uint8_t TiltActive;
static uint8_t TiltCentered;
static uint8_t TrackArmed;
static uint16_t TrackPanUs;
static uint16_t TrackTiltUs;
static uint32_t TrackDeadline;
static uint32_t TrackLastRampMs;

static void Pan_Start(uint16_t PulseUs);
static void Tilt_Start(uint16_t PulseUs);
static void Track_PanStart(void);
static void Track_TiltStart(void);
static void Track_Ramp(void);

void Pan_MillisTick(void)
{
	PanMilliseconds ++;
}

static void Pan_PinLow(void)
{
	GPIO_InitTypeDef GPIO_InitStructure;

	GPIO_InitStructure.GPIO_Mode = GPIO_Mode_Out_PP;
	GPIO_InitStructure.GPIO_Pin = GPIO_Pin_6;
	GPIO_InitStructure.GPIO_Speed = GPIO_Speed_2MHz;
	GPIO_Init(GPIOA, &GPIO_InitStructure);
	GPIO_ResetBits(GPIOA, GPIO_Pin_6);
}

static void Pan_Stop(void)
{
	TIM_CCxCmd(TIM3, TIM_Channel_1, TIM_CCx_Disable);
	if (!TiltActive) TIM_Cmd(TIM3, DISABLE);
	Pan_PinLow();
	PanActive = 0;
	PanCentered = 0;
	/* Keep the last emitted pulse for restart; OFF still disables the pin. */
}

static void Tilt_PinLow(void)
{
	GPIO_InitTypeDef GPIO_InitStructure;

	GPIO_InitStructure.GPIO_Mode = GPIO_Mode_Out_PP;
	GPIO_InitStructure.GPIO_Pin = GPIO_Pin_7;
	GPIO_InitStructure.GPIO_Speed = GPIO_Speed_2MHz;
	GPIO_Init(GPIOA, &GPIO_InitStructure);
	GPIO_ResetBits(GPIOA, GPIO_Pin_7);
}

static void Tilt_Stop(void)
{
	TIM_CCxCmd(TIM3, TIM_Channel_2, TIM_CCx_Disable);
	if (!PanActive) TIM_Cmd(TIM3, DISABLE);
	Tilt_PinLow();
	TiltActive = 0;
	TiltCentered = 0;
	/* This is a commanded position, not measured shaft feedback. */
}

static void Track_Stop(void)
{
	TrackArmed = 0;
	Pan_Stop();
	Tilt_Stop();
}

static void Track_CheckTimeout(void)
{
	if (TrackArmed && ((int32_t)(PanMilliseconds - TrackDeadline) >= 0))
	{
		Track_Stop();
	}
}

static void Track_Refresh(void)
{
	TrackDeadline = PanMilliseconds + PAN_TIMEOUT_MS;
	if (PanActive) PanDeadline = TrackDeadline;
	if (TiltActive) TiltDeadline = TrackDeadline;
}

static void Track_SendPosition(const char *Axis, uint16_t PulseUs)
{
	Serial_SendString("TRK_");
	Serial_SendString(Axis);
	Serial_SendString("=");
	Serial_SendNumber(PulseUs, 4);
	Serial_SendString("US\r\n");
}

static void Track_Step(uint8_t IsPan, int16_t DeltaUs)
{
	uint16_t *Target = IsPan ? &TrackPanUs : &TrackTiltUs;
	uint16_t Minimum = IsPan ? TRACK_PAN_MIN_US : TRACK_TILT_MIN_US;
	uint16_t Maximum = IsPan ? TRACK_PAN_MAX_US : TRACK_TILT_MAX_US;
	int32_t Next;
	if (!TrackArmed)
	{
		Serial_SendString("ERR TRK_NOT_ARMED\r\n");
		return;
	}
	Next = (int32_t)*Target + DeltaUs;
	if (Next < Minimum) Next = Minimum;
	if (Next > Maximum) Next = Maximum;
	*Target = (uint16_t)Next;
	if (IsPan) Track_PanStart();
	else Track_TiltStart();
	Track_Refresh();
	Track_SendPosition(IsPan ? "PAN" : "TILT", *Target);
}

static void Pan_CheckTimeout(void)
{
	if (PanActive && ((int32_t)(PanMilliseconds - PanDeadline) >= 0))
	{
		Pan_Stop();
	}
}

static void Tilt_CheckTimeout(void)
{
	if (TiltActive && ((int32_t)(PanMilliseconds - TiltDeadline) >= 0))
	{
		Tilt_Stop();
	}
}

static void Pan_Init(void)
{
	RCC_ClocksTypeDef Clocks;
	TIM_TimeBaseInitTypeDef TimeBase;
	TIM_OCInitTypeDef OutputCompare;
	uint32_t TimerClock;

	RCC_APB2PeriphClockCmd(RCC_APB2Periph_GPIOA, ENABLE);
	RCC_APB1PeriphClockCmd(RCC_APB1Periph_TIM3, ENABLE);
	Tilt_PinLow();
	Pan_PinLow();
	RCC_GetClocksFreq(&Clocks);
	TimerClock = Clocks.PCLK1_Frequency;
	if (Clocks.PCLK1_Frequency != Clocks.HCLK_Frequency)
	{
		TimerClock *= 2U;
	}
	/* A 1 MHz counter makes each compare count one microsecond. */
	if ((TimerClock < 1000000U) || ((TimerClock % 1000000U) != 0U))
	{
		return;
	}

	TIM_TimeBaseStructInit(&TimeBase);
	TimeBase.TIM_Period = PAN_PERIOD_US - 1U;
	TimeBase.TIM_Prescaler = TimerClock / 1000000U - 1U;
	TIM_TimeBaseInit(TIM3, &TimeBase);

	TIM_OCStructInit(&OutputCompare);
	OutputCompare.TIM_OCMode = TIM_OCMode_PWM1;
	OutputCompare.TIM_OutputState = TIM_OutputState_Disable;
	OutputCompare.TIM_OCPolarity = TIM_OCPolarity_High;
	OutputCompare.TIM_Pulse = PAN_CENTER_US;
	TIM_OC1Init(TIM3, &OutputCompare);
	TIM_OC1PreloadConfig(TIM3, TIM_OCPreload_Enable);
	TIM_OC2Init(TIM3, &OutputCompare);
	TIM_OC2PreloadConfig(TIM3, TIM_OCPreload_Enable);
	TIM_ARRPreloadConfig(TIM3, ENABLE);
	TIM_Cmd(TIM3, DISABLE);
	PanReady = 1;
	TiltReady = 1;
}

static void Pan_Start(uint16_t PulseUs)
{
	GPIO_InitTypeDef GPIO_InitStructure;

	TrackArmed = 0;
	Tilt_Stop();
	TIM_Cmd(TIM3, DISABLE);
	TIM_CCxCmd(TIM3, TIM_Channel_1, TIM_CCx_Disable);
	TIM_SetCompare1(TIM3, PulseUs);
	TIM_SetCounter(TIM3, 0);
	TIM_GenerateEvent(TIM3, TIM_EventSource_Update);
	GPIO_InitStructure.GPIO_Mode = GPIO_Mode_AF_PP;
	GPIO_InitStructure.GPIO_Pin = GPIO_Pin_6;
	GPIO_InitStructure.GPIO_Speed = GPIO_Speed_2MHz;
	GPIO_Init(GPIOA, &GPIO_InitStructure);
	TIM_CCxCmd(TIM3, TIM_Channel_1, TIM_CCx_Enable);
	TIM_Cmd(TIM3, ENABLE);
	PanPulseUs = PulseUs;
	PanDeadline = PanMilliseconds + PAN_TIMEOUT_MS;
	PanActive = 1;
}

static void Tilt_Start(uint16_t PulseUs)
{
	GPIO_InitTypeDef GPIO_InitStructure;

	TrackArmed = 0;
	Pan_Stop();
	TIM_Cmd(TIM3, DISABLE);
	TIM_CCxCmd(TIM3, TIM_Channel_2, TIM_CCx_Disable);
	TIM_SetCompare2(TIM3, PulseUs);
	TIM_SetCounter(TIM3, 0);
	TIM_GenerateEvent(TIM3, TIM_EventSource_Update);
	GPIO_InitStructure.GPIO_Mode = GPIO_Mode_AF_PP;
	GPIO_InitStructure.GPIO_Pin = GPIO_Pin_7;
	GPIO_InitStructure.GPIO_Speed = GPIO_Speed_2MHz;
	GPIO_Init(GPIOA, &GPIO_InitStructure);
	TIM_CCxCmd(TIM3, TIM_Channel_2, TIM_CCx_Enable);
	TIM_Cmd(TIM3, ENABLE);
	TiltPulseUs = PulseUs;
	TiltDeadline = PanMilliseconds + PAN_TIMEOUT_MS;
	TiltActive = 1;
}

static void Track_PanStart(void)
{
	GPIO_InitTypeDef GPIO_InitStructure;
	if (PanActive) return;
	GPIO_InitStructure.GPIO_Mode = GPIO_Mode_AF_PP;
	GPIO_InitStructure.GPIO_Pin = GPIO_Pin_6;
	GPIO_InitStructure.GPIO_Speed = GPIO_Speed_2MHz;
	GPIO_Init(GPIOA, &GPIO_InitStructure);
	TIM_SetCompare1(TIM3, PanPulseUs);
	TIM_GenerateEvent(TIM3, TIM_EventSource_Update);
	if (!TiltActive)
	{
		TIM_SetCounter(TIM3, 0);
	}
	TIM_CCxCmd(TIM3, TIM_Channel_1, TIM_CCx_Enable);
	TIM_Cmd(TIM3, ENABLE);
	PanActive = 1;
}

static void Track_TiltStart(void)
{
	GPIO_InitTypeDef GPIO_InitStructure;
	if (TiltActive) return;
	GPIO_InitStructure.GPIO_Mode = GPIO_Mode_AF_PP;
	GPIO_InitStructure.GPIO_Pin = GPIO_Pin_7;
	GPIO_InitStructure.GPIO_Speed = GPIO_Speed_2MHz;
	GPIO_Init(GPIOA, &GPIO_InitStructure);
	TIM_SetCompare2(TIM3, TiltPulseUs);
	TIM_GenerateEvent(TIM3, TIM_EventSource_Update);
	if (!PanActive)
	{
		TIM_SetCounter(TIM3, 0);
	}
	TIM_CCxCmd(TIM3, TIM_Channel_2, TIM_CCx_Enable);
	TIM_Cmd(TIM3, ENABLE);
	TiltActive = 1;
}

static uint16_t Track_Approach(uint16_t Current, uint16_t Target)
{
	if (Current < Target)
	{
		uint16_t Gap = Target - Current;
		return Current + (Gap < TRACK_RAMP_STEP_US ? Gap : TRACK_RAMP_STEP_US);
	}
	if (Current > Target)
	{
		uint16_t Gap = Current - Target;
		return Current - (Gap < TRACK_RAMP_STEP_US ? Gap : TRACK_RAMP_STEP_US);
	}
	return Current;
}

static void Track_Ramp(void)
{
	if (!TrackArmed ||
	    (uint32_t)(PanMilliseconds - TrackLastRampMs) < TRACK_RAMP_PERIOD_MS)
		return;
	/* Never catch up with a burst after a stalled loop. */
	TrackLastRampMs = PanMilliseconds;
	if (PanActive)
	{
		PanPulseUs = Track_Approach(PanPulseUs, TrackPanUs);
		TIM_SetCompare1(TIM3, PanPulseUs);
	}
	if (TiltActive)
	{
		TiltPulseUs = Track_Approach(TiltPulseUs, TrackTiltUs);
		TIM_SetCompare2(TIM3, TiltPulseUs);
	}
}

static void Pan_SendStatus(void)
{
	if (!PanActive)
	{
		Serial_SendString("PAN_PWM=OFF\r\n");
	}
	else
	{
		Serial_SendString("PAN_PWM=");
		Serial_SendNumber(PanPulseUs, 4);
		Serial_SendString("US\r\n");
	}
}

static uint16_t Pan_LeftCalibrationPulse(const char *Command)
{
	static const char * const Commands[] = {
		"PAN +550", "PAN +600", "PAN +650", "PAN +700", "PAN +750",
		"PAN +800", "PAN +850", "PAN +900", "PAN +950", "PAN +1000"
	};
	uint8_t i;

	/* Calibration is explicit and bounded; no free-form pulse value is accepted. */
	for (i = 0; i < sizeof(Commands) / sizeof(Commands[0]); i ++)
	{
		if (strcmp(Command, Commands[i]) == 0)
		{
			return PAN_CENTER_US + PAN_EDGE_STEP_US + (i + 1U) * PAN_STEP_US;
		}
	}
	return 0;
}

static uint16_t Pan_RightCalibrationPulse(const char *Command)
{
	static const char * const Commands[] = {
		"PAN -550", "PAN -600", "PAN -650", "PAN -700", "PAN -750",
		"PAN -800", "PAN -850", "PAN -900", "PAN -950", "PAN -1000"
	};
	uint8_t i;

	for (i = 0; i < sizeof(Commands) / sizeof(Commands[0]); i ++)
	{
		if (strcmp(Command, Commands[i]) == 0)
		{
			return PAN_CENTER_US - PAN_EDGE_STEP_US - (i + 1U) * PAN_STEP_US;
		}
	}
	return 0;
}

static uint16_t Tilt_CalibrationPulse(const char *Command)
{
	static const char * const BackwardCommands[] = {
		"TILT -450", "TILT -500", "TILT -550", "TILT -600",
		"TILT -650", "TILT -700", "TILT -750"
	};
	static const char * const ForwardCommands[] = {
		"TILT +450", "TILT +500", "TILT +550", "TILT +600",
		"TILT +650", "TILT +700", "TILT +750"
	};
	uint8_t i;

	/* Only these fixed calibration positions can extend the accepted range. */
	for (i = 0; i < sizeof(BackwardCommands) / sizeof(BackwardCommands[0]); i ++)
	{
		if (strcmp(Command, BackwardCommands[i]) == 0)
		{
			return PAN_CENTER_US - PAN_NEAR_EDGE_STEP_US - i * PAN_STEP_US;
		}
		if (strcmp(Command, ForwardCommands[i]) == 0)
		{
			return PAN_CENTER_US + PAN_NEAR_EDGE_STEP_US + i * PAN_STEP_US;
		}
	}
	return 0;
}

static void Pan_ProbePin(void)
{
	uint32_t Start = PanMilliseconds;
	uint8_t LastLevel = GPIO_ReadInputDataBit(GPIOA, GPIO_Pin_6);
	uint8_t Transitions = 0;

	/* Sample the PA6 pad across several PWM periods, without extending output time. */
	while ((uint32_t)(PanMilliseconds - Start) < PAN_PROBE_MS)
	{
		uint8_t Level = GPIO_ReadInputDataBit(GPIOA, GPIO_Pin_6);
		if (Level != LastLevel)
		{
			Transitions ++;
			LastLevel = Level;
		}
	}
	Serial_SendString(Transitions >= 4U ? "PAN_PIN=TOGGLE\r\n" :
	                                     "PAN_PIN=NO_TOGGLE\r\n");
}

static void Tilt_SendStatus(void)
{
	if (!TiltActive)
	{
		Serial_SendString("TILT_PWM=OFF\r\n");
	}
	else
	{
		Serial_SendString("TILT_PWM=");
		Serial_SendNumber(TiltPulseUs, 4);
		Serial_SendString("US\r\n");
	}
}

static void Tilt_ProbePin(void)
{
	uint32_t Start = PanMilliseconds;
	uint8_t LastLevel = GPIO_ReadInputDataBit(GPIOA, GPIO_Pin_7);
	uint8_t Transitions = 0;

	while ((uint32_t)(PanMilliseconds - Start) < PAN_PROBE_MS)
	{
		uint8_t Level = GPIO_ReadInputDataBit(GPIOA, GPIO_Pin_7);
		if (Level != LastLevel)
		{
			Transitions ++;
			LastLevel = Level;
		}
	}
	Serial_SendString(Transitions >= 4U ? "TILT_PIN=TOGGLE\r\n" :
	                                     "TILT_PIN=NO_TOGGLE\r\n");
}

static void BoardLED_Init(void)
{
	GPIO_InitTypeDef GPIO_InitStructure;

	RCC_APB2PeriphClockCmd(RCC_APB2Periph_GPIOC, ENABLE);

	GPIO_InitStructure.GPIO_Mode = GPIO_Mode_Out_PP;
	GPIO_InitStructure.GPIO_Pin = GPIO_Pin_13;
	GPIO_InitStructure.GPIO_Speed = GPIO_Speed_2MHz;
	GPIO_Init(GPIOC, &GPIO_InitStructure);

	/* The Blue Pill PC13 LED is active low. Start with it off. */
	GPIO_SetBits(GPIOC, GPIO_Pin_13);
}

static uint8_t BoardLED_IsOn(void)
{
	return GPIO_ReadOutputDataBit(GPIOC, GPIO_Pin_13) == Bit_RESET;
}

static void BoardLED_SetOn(uint8_t On)
{
	/* PC13 drives the on-board LED low to turn it on. */
	if (On)
	{
		GPIO_ResetBits(GPIOC, GPIO_Pin_13);
	}
	else
	{
		GPIO_SetBits(GPIOC, GPIO_Pin_13);
	}
}

static void ProcessCommand(const char *Command)
{
	Track_CheckTimeout();
	Pan_CheckTimeout();
	Tilt_CheckTimeout();
	if (strcmp(Command, "TRK STOP") == 0)
	{
		Track_Stop();
		Serial_SendString("TRK=OFF\r\n");
	}
	else if (strcmp(Command, "TRK?") == 0)
	{
		Serial_SendString(TrackArmed ? "TRK=ARMED\r\n" : "TRK=OFF\r\n");
	}
	else if (strcmp(Command, "TRK POS?") == 0)
	{
		if (!PanPulseUs || !TiltPulseUs)
			Serial_SendString("TRK_POS=UNKNOWN\r\n");
		else
		{
			Serial_SendString("TRK_POS=");
			Serial_SendNumber(PanPulseUs, 4);
			Serial_SendString(",");
			Serial_SendNumber(TiltPulseUs, 4);
			Serial_SendString("\r\n");
		}
	}
	else if (strcmp(Command, "TRK CENTER") == 0)
	{
		Track_Stop();
		if (!PanReady || !TiltReady)
			Serial_SendString("ERR TRK_UNAVAILABLE\r\n");
		else
		{
			/* Unknown after reset: only this explicit command may initialize. */
			if (!PanPulseUs) PanPulseUs = PAN_CENTER_US;
			if (!TiltPulseUs) TiltPulseUs = PAN_CENTER_US;
			TrackPanUs = TrackTiltUs = PAN_CENTER_US;
			TrackArmed = 1;
			TrackLastRampMs = PanMilliseconds;
			Track_PanStart();
			Track_TiltStart();
			Track_Refresh();
			Serial_SendString("TRK=CENTERING\r\n");
		}
	}
	else if (strcmp(Command, "TRK ARM") == 0)
	{
		Track_Stop();
		if (!PanReady || !TiltReady)
		{
			Serial_SendString("ERR TRK_UNAVAILABLE\r\n");
		}
		else if (!PanPulseUs || !TiltPulseUs)
		{
			Serial_SendString("ERR TRK_POSITION_UNKNOWN\r\n");
		}
		else
		{
			TrackPanUs = PanPulseUs;
			TrackTiltUs = TiltPulseUs;
			TrackArmed = 1;
			TrackLastRampMs = PanMilliseconds;
			Track_Refresh();
			Serial_SendString("TRK=ARMED\r\n");
		}
	}
	else if (strcmp(Command, "TRK KEEP") == 0)
	{
		if (!TrackArmed) Serial_SendString("ERR TRK_NOT_ARMED\r\n");
		else
		{
			Track_Refresh();
			Serial_SendString("TRK=ARMED\r\n");
		}
	}
	else if (strcmp(Command, "TRK P+") == 0) Track_Step(1, TRACK_TARGET_STEP_US);
	else if (strcmp(Command, "TRK P-") == 0) Track_Step(1, -(int16_t)TRACK_TARGET_STEP_US);
	else if (strcmp(Command, "TRK T+") == 0) Track_Step(0, TRACK_TARGET_STEP_US);
	else if (strcmp(Command, "TRK T-") == 0) Track_Step(0, -(int16_t)TRACK_TARGET_STEP_US);
	else if (strcmp(Command, "PING") == 0)
	{
		Serial_SendString("PONG\r\n");
	}
	else if (strcmp(Command, "LED ON") == 0)
	{
		BoardLED_SetOn(1);
		Serial_SendString("OK\r\n");
	}
	else if (strcmp(Command, "LED OFF") == 0)
	{
		BoardLED_SetOn(0);
		Serial_SendString("OK\r\n");
	}
	else if (strcmp(Command, "LED?") == 0)
	{
		if (BoardLED_IsOn())
		{
			Serial_SendString("LED=ON\r\n");
		}
		else
		{
			Serial_SendString("LED=OFF\r\n");
		}
	}
	else if (strcmp(Command, "PAN STOP") == 0)
	{
		Track_Stop();
		Pan_SendStatus();
	}
	else if (strcmp(Command, "PAN?") == 0)
	{
		Pan_SendStatus();
	}
	else if (strcmp(Command, "PAN PROBE") == 0)
	{
		if (!PanActive)
		{
			Serial_SendString("ERR PAN_INACTIVE\r\n");
		}
		else
		{
			Pan_ProbePin();
		}
	}
	else if (strcmp(Command, "PAN CENTER") == 0)
	{
		if (!PanReady)
		{
			Serial_SendString("ERR PAN_UNAVAILABLE\r\n");
		}
		else
		{
			Pan_Start(PAN_CENTER_US);
			PanCentered = 1;
			Pan_SendStatus();
		}
	}
	else if ((strcmp(Command, "PAN -100") == 0) ||
	         (strcmp(Command, "PAN -50") == 0) ||
	         (strcmp(Command, "PAN -150") == 0) ||
	         (strcmp(Command, "PAN -200") == 0) ||
	         (strcmp(Command, "PAN -250") == 0) ||
	         (strcmp(Command, "PAN -300") == 0) ||
	         (strcmp(Command, "PAN -350") == 0) ||
	         (strcmp(Command, "PAN -400") == 0) ||
	         (strcmp(Command, "PAN -450") == 0) ||
	         (strcmp(Command, "PAN -500") == 0) ||
	         (strcmp(Command, "PAN +50") == 0) ||
	         (strcmp(Command, "PAN +100") == 0) ||
	         (strcmp(Command, "PAN +150") == 0) ||
	         (strcmp(Command, "PAN +200") == 0) ||
	         (strcmp(Command, "PAN +250") == 0) ||
	         (strcmp(Command, "PAN +300") == 0) ||
	         (strcmp(Command, "PAN +350") == 0) ||
	         (strcmp(Command, "PAN +400") == 0) ||
	         (strcmp(Command, "PAN +450") == 0) ||
	         (strcmp(Command, "PAN +500") == 0))
	{
		if (!PanReady)
		{
			Serial_SendString("ERR PAN_UNAVAILABLE\r\n");
		}
		else if (!PanActive || !PanCentered)
		{
			Serial_SendString("ERR PAN_CENTER_FIRST\r\n");
		}
		else
		{
			uint16_t PulseUs;
			if (strcmp(Command, "PAN -100") == 0)
			{
				PulseUs = PAN_CENTER_US - PAN_TEST_STEP_US;
			}
			else if (strcmp(Command, "PAN -50") == 0)
			{
				PulseUs = PAN_CENTER_US - PAN_STEP_US;
			}
			else if (strcmp(Command, "PAN -150") == 0)
			{
				PulseUs = PAN_CENTER_US - PAN_WIDE_STEP_US;
			}
			else if (strcmp(Command, "PAN -200") == 0)
			{
				PulseUs = PAN_CENTER_US - PAN_FAR_STEP_US;
			}
			else if (strcmp(Command, "PAN -250") == 0)
			{
				PulseUs = PAN_CENTER_US - PAN_NEXT_STEP_US;
			}
			else if (strcmp(Command, "PAN -300") == 0)
			{
				PulseUs = PAN_CENTER_US - PAN_FURTHER_STEP_US;
			}
			else if (strcmp(Command, "PAN -350") == 0)
			{
				PulseUs = PAN_CENTER_US - PAN_MORE_STEP_US;
			}
			else if (strcmp(Command, "PAN -400") == 0)
			{
				PulseUs = PAN_CENTER_US - PAN_MORE2_STEP_US;
			}
			else if (strcmp(Command, "PAN -450") == 0)
			{
				PulseUs = PAN_CENTER_US - PAN_NEAR_EDGE_STEP_US;
			}
			else if (strcmp(Command, "PAN -500") == 0)
			{
				PulseUs = PAN_CENTER_US - PAN_EDGE_STEP_US;
			}
			else if (strcmp(Command, "PAN +50") == 0)
			{
				PulseUs = PAN_CENTER_US + PAN_STEP_US;
			}
			else if (strcmp(Command, "PAN +100") == 0)
			{
				PulseUs = PAN_CENTER_US + PAN_TEST_STEP_US;
			}
			else if (strcmp(Command, "PAN +150") == 0)
			{
				PulseUs = PAN_CENTER_US + PAN_WIDE_STEP_US;
			}
			else if (strcmp(Command, "PAN +200") == 0)
			{
				PulseUs = PAN_CENTER_US + PAN_FAR_STEP_US;
			}
			else if (strcmp(Command, "PAN +250") == 0)
			{
				PulseUs = PAN_CENTER_US + PAN_NEXT_STEP_US;
			}
			else if (strcmp(Command, "PAN +300") == 0)
			{
				PulseUs = PAN_CENTER_US + PAN_FURTHER_STEP_US;
			}
			else if (strcmp(Command, "PAN +350") == 0)
			{
				PulseUs = PAN_CENTER_US + PAN_MORE_STEP_US;
			}
			else if (strcmp(Command, "PAN +400") == 0)
			{
				PulseUs = PAN_CENTER_US + PAN_MORE2_STEP_US;
			}
			else if (strcmp(Command, "PAN +450") == 0)
			{
				PulseUs = PAN_CENTER_US + PAN_NEAR_EDGE_STEP_US;
			}
			else
			{
				PulseUs = PAN_CENTER_US + PAN_EDGE_STEP_US;
			}
			Pan_Start(PulseUs);
			PanCentered = 0;
			Pan_SendStatus();
		}
	}
	else if (Pan_LeftCalibrationPulse(Command) != 0U)
	{
		if (!PanReady)
		{
			Serial_SendString("ERR PAN_UNAVAILABLE\r\n");
		}
		else if (!PanActive || !PanCentered)
		{
			Serial_SendString("ERR PAN_CENTER_FIRST\r\n");
		}
		else
		{
			Pan_Start(Pan_LeftCalibrationPulse(Command));
			PanCentered = 0;
			Pan_SendStatus();
		}
	}
	else if (Pan_RightCalibrationPulse(Command) != 0U)
	{
		if (!PanReady)
		{
			Serial_SendString("ERR PAN_UNAVAILABLE\r\n");
		}
		else if (!PanActive || !PanCentered)
		{
			Serial_SendString("ERR PAN_CENTER_FIRST\r\n");
		}
		else
		{
			Pan_Start(Pan_RightCalibrationPulse(Command));
			PanCentered = 0;
			Pan_SendStatus();
		}
	}
	else if (strcmp(Command, "TILT STOP") == 0)
	{
		Track_Stop();
		Tilt_SendStatus();
	}
	else if (strcmp(Command, "TILT?") == 0)
	{
		Tilt_SendStatus();
	}
	else if (strcmp(Command, "TILT PROBE") == 0)
	{
		if (!TiltActive)
		{
			Serial_SendString("ERR TILT_INACTIVE\r\n");
		}
		else
		{
			Tilt_ProbePin();
		}
	}
	else if (strcmp(Command, "TILT CENTER") == 0)
	{
		if (!TiltReady)
		{
			Serial_SendString("ERR TILT_UNAVAILABLE\r\n");
		}
		else
		{
			Tilt_Start(PAN_CENTER_US);
			TiltCentered = 1;
			Tilt_SendStatus();
		}
	}
	else if ((strcmp(Command, "TILT -50") == 0) ||
	         (strcmp(Command, "TILT -100") == 0) ||
	         (strcmp(Command, "TILT -150") == 0) ||
	         (strcmp(Command, "TILT -200") == 0) ||
	         (strcmp(Command, "TILT -250") == 0) ||
	         (strcmp(Command, "TILT -300") == 0) ||
	         (strcmp(Command, "TILT -350") == 0) ||
	         (strcmp(Command, "TILT -400") == 0) ||
	         (strcmp(Command, "TILT +50") == 0) ||
	         (strcmp(Command, "TILT +100") == 0) ||
	         (strcmp(Command, "TILT +150") == 0) ||
	         (strcmp(Command, "TILT +200") == 0) ||
	         (strcmp(Command, "TILT +250") == 0) ||
	         (strcmp(Command, "TILT +300") == 0) ||
	         (strcmp(Command, "TILT +350") == 0) ||
	         (strcmp(Command, "TILT +400") == 0))
	{
		if (!TiltReady)
		{
			Serial_SendString("ERR TILT_UNAVAILABLE\r\n");
		}
		else if (!TiltActive || !TiltCentered)
		{
			Serial_SendString("ERR TILT_CENTER_FIRST\r\n");
		}
		else
		{
			uint16_t PulseUs;
			if (strcmp(Command, "TILT -50") == 0)
			{
				PulseUs = PAN_CENTER_US - PAN_STEP_US;
			}
			else if (strcmp(Command, "TILT -100") == 0)
			{
				PulseUs = PAN_CENTER_US - PAN_TEST_STEP_US;
			}
			else if (strcmp(Command, "TILT -150") == 0)
			{
				PulseUs = PAN_CENTER_US - PAN_WIDE_STEP_US;
			}
			else if (strcmp(Command, "TILT -200") == 0)
			{
				PulseUs = PAN_CENTER_US - PAN_FAR_STEP_US;
			}
			else if (strcmp(Command, "TILT -250") == 0)
			{
				PulseUs = PAN_CENTER_US - PAN_NEXT_STEP_US;
			}
			else if (strcmp(Command, "TILT -300") == 0)
			{
				PulseUs = PAN_CENTER_US - PAN_FURTHER_STEP_US;
			}
			else if (strcmp(Command, "TILT -350") == 0)
			{
				PulseUs = PAN_CENTER_US - PAN_MORE_STEP_US;
			}
			else if (strcmp(Command, "TILT -400") == 0)
			{
				PulseUs = PAN_CENTER_US - PAN_MORE2_STEP_US;
			}
			else if (strcmp(Command, "TILT +50") == 0)
			{
				PulseUs = PAN_CENTER_US + PAN_STEP_US;
			}
			else if (strcmp(Command, "TILT +100") == 0)
			{
				PulseUs = PAN_CENTER_US + PAN_TEST_STEP_US;
			}
			else if (strcmp(Command, "TILT +150") == 0)
			{
				PulseUs = PAN_CENTER_US + PAN_WIDE_STEP_US;
			}
			else if (strcmp(Command, "TILT +200") == 0)
			{
				PulseUs = PAN_CENTER_US + PAN_FAR_STEP_US;
			}
			else if (strcmp(Command, "TILT +250") == 0)
			{
				PulseUs = PAN_CENTER_US + PAN_NEXT_STEP_US;
			}
			else if (strcmp(Command, "TILT +300") == 0)
			{
				PulseUs = PAN_CENTER_US + PAN_FURTHER_STEP_US;
			}
			else if (strcmp(Command, "TILT +350") == 0)
			{
				PulseUs = PAN_CENTER_US + PAN_MORE_STEP_US;
			}
			else
			{
				PulseUs = PAN_CENTER_US + PAN_MORE2_STEP_US;
			}
			Tilt_Start(PulseUs);
			TiltCentered = 0;
			Tilt_SendStatus();
		}
	}
	else if (Tilt_CalibrationPulse(Command) != 0U)
	{
		if (!TiltReady)
		{
			Serial_SendString("ERR TILT_UNAVAILABLE\r\n");
		}
		else if (!TiltActive || !TiltCentered)
		{
			Serial_SendString("ERR TILT_CENTER_FIRST\r\n");
		}
		else
		{
			Tilt_Start(Tilt_CalibrationPulse(Command));
			TiltCentered = 0;
			Tilt_SendStatus();
		}
	}
	else
	{
		Serial_SendString("ERR\r\n");
	}
}

static void ProcessReceivedByte(uint8_t Byte)
{
	if ((Byte == '\r') || (Byte == '\n'))
	{
		if (CommandLength != 0)
		{
			CommandBuffer[CommandLength] = '\0';
			ProcessCommand(CommandBuffer);
			CommandLength = 0;
		}
		return;
	}

	if ((Byte < 0x20) || (Byte > 0x7e))
	{
		CommandLength = 0;
		return;
	}

	if (CommandLength < (COMMAND_BUFFER_SIZE - 1))
	{
		CommandBuffer[CommandLength] = (char)Byte;
		CommandLength ++;
	}
	else
	{
		CommandLength = 0;
		Serial_SendString("ERR\r\n");
	}
}

int main(void)
{
	BoardLED_Init();
	Serial_Init();
	Pan_Init();
	SystemCoreClockUpdate();
	if (SysTick_Config(SystemCoreClock / 1000U) != 0)
	{
		PanReady = 0;
		TiltReady = 0;
	}

	while (1)
	{
		Track_CheckTimeout();
		Track_Ramp();
		Pan_CheckTimeout();
		Tilt_CheckTimeout();
		while (Serial_GetRxFlag())
		{
			ProcessReceivedByte(Serial_GetRxData());
			Track_CheckTimeout();
			Track_Ramp();
			Pan_CheckTimeout();
			Tilt_CheckTimeout();
		}
	}
}

#include "Serial.h"
#include <stdarg.h>

#define SERIAL_RX_BUFFER_SIZE 64

static volatile uint8_t Serial_RxBuffer[SERIAL_RX_BUFFER_SIZE];
static volatile uint8_t Serial_RxHead;
static volatile uint8_t Serial_RxTail;

void Serial_Init(void)
{
	GPIO_InitTypeDef GPIO_InitStructure;
	USART_InitTypeDef USART_InitStructure;
	NVIC_InitTypeDef NVIC_InitStructure;

	RCC_APB2PeriphClockCmd(RCC_APB2Periph_USART1, ENABLE);
	RCC_APB2PeriphClockCmd(RCC_APB2Periph_GPIOA, ENABLE);

	GPIO_InitStructure.GPIO_Mode = GPIO_Mode_AF_PP;
	GPIO_InitStructure.GPIO_Pin = GPIO_Pin_9;
	GPIO_InitStructure.GPIO_Speed = GPIO_Speed_50MHz;
	GPIO_Init(GPIOA, &GPIO_InitStructure);

	GPIO_InitStructure.GPIO_Mode = GPIO_Mode_IPU;
	GPIO_InitStructure.GPIO_Pin = GPIO_Pin_10;
	GPIO_InitStructure.GPIO_Speed = GPIO_Speed_50MHz;
	GPIO_Init(GPIOA, &GPIO_InitStructure);

	USART_InitStructure.USART_BaudRate = 115200;
	USART_InitStructure.USART_HardwareFlowControl = USART_HardwareFlowControl_None;
	USART_InitStructure.USART_Mode = USART_Mode_Tx | USART_Mode_Rx;
	USART_InitStructure.USART_Parity = USART_Parity_No;
	USART_InitStructure.USART_StopBits = USART_StopBits_1;
	USART_InitStructure.USART_WordLength = USART_WordLength_8b;
	USART_Init(USART1, &USART_InitStructure);

	USART_ITConfig(USART1, USART_IT_RXNE, ENABLE);

	NVIC_PriorityGroupConfig(NVIC_PriorityGroup_2);
	NVIC_InitStructure.NVIC_IRQChannel = USART1_IRQn;
	NVIC_InitStructure.NVIC_IRQChannelCmd = ENABLE;
	NVIC_InitStructure.NVIC_IRQChannelPreemptionPriority = 1;
	NVIC_InitStructure.NVIC_IRQChannelSubPriority = 1;
	NVIC_Init(&NVIC_InitStructure);

	USART_Cmd(USART1, ENABLE);
}

void Serial_SendByte(uint8_t Byte)
{
	USART_SendData(USART1, Byte);
	while (USART_GetFlagStatus(USART1, USART_FLAG_TXE) == RESET);
}

void Serial_SendArray(const uint8_t *Array, uint16_t Length)
{
	uint16_t i;
	for (i = 0; i < Length; i ++)
	{
		Serial_SendByte(Array[i]);
	}
}

void Serial_SendString(const char *String)
{
	uint16_t i;
	for (i = 0; String[i] != '\0'; i ++)
	{
		Serial_SendByte((uint8_t)String[i]);
	}
}

static uint32_t Serial_Pow(uint32_t X, uint32_t Y)
{
	uint32_t Result = 1;
	while (Y --)
	{
		Result *= X;
	}
	return Result;
}

void Serial_SendNumber(uint32_t Number, uint8_t Length)
{
	uint8_t i;
	for (i = 0; i < Length; i ++)
	{
		Serial_SendByte((uint8_t)(Number / Serial_Pow(10, Length - i - 1) % 10 + '0'));
	}
}

int fputc(int ch, FILE *f)
{
	(void)f;
	Serial_SendByte((uint8_t)ch);
	return ch;
}

void Serial_Printf(const char *format, ...)
{
	char String[100];
	va_list arg;

	va_start(arg, format);
	vsprintf(String, format, arg);
	va_end(arg);
	Serial_SendString(String);
}

uint8_t Serial_GetRxFlag(void)
{
	return Serial_RxHead != Serial_RxTail;
}

uint8_t Serial_GetRxData(void)
{
	uint8_t Data;

	if (Serial_RxHead == Serial_RxTail)
	{
		return 0;
	}

	Data = Serial_RxBuffer[Serial_RxTail];
	Serial_RxTail = (uint8_t)((Serial_RxTail + 1) % SERIAL_RX_BUFFER_SIZE);
	return Data;
}

void USART1_IRQHandler(void)
{
	if (USART_GetITStatus(USART1, USART_IT_RXNE) == SET)
	{
		uint8_t Data = (uint8_t)USART_ReceiveData(USART1);
		uint8_t NextHead = (uint8_t)((Serial_RxHead + 1) % SERIAL_RX_BUFFER_SIZE);

		if (NextHead != Serial_RxTail)
		{
			Serial_RxBuffer[Serial_RxHead] = Data;
			Serial_RxHead = NextHead;
		}
	}
}

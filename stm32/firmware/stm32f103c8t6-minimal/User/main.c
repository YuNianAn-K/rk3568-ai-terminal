#include "stm32f10x.h"
#include "Delay.h"

#define LED_GPIO_PORT GPIOC
#define LED_GPIO_PIN  GPIO_Pin_13

int main(void)
{
	GPIO_InitTypeDef gpio_init;

	RCC_APB2PeriphClockCmd(RCC_APB2Periph_GPIOC, ENABLE);

	/* The minimum-system-board LED on PC13 is active low. */
	GPIO_SetBits(LED_GPIO_PORT, LED_GPIO_PIN);
	gpio_init.GPIO_Mode = GPIO_Mode_Out_PP;
	gpio_init.GPIO_Pin = LED_GPIO_PIN;
	gpio_init.GPIO_Speed = GPIO_Speed_50MHz;
	GPIO_Init(LED_GPIO_PORT, &gpio_init);

	while (1)
	{
		GPIO_ResetBits(LED_GPIO_PORT, LED_GPIO_PIN);
		Delay_ms(500);
		GPIO_SetBits(LED_GPIO_PORT, LED_GPIO_PIN);
		Delay_ms(500);
	}
}

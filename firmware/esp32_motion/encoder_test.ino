// SPARC rover — encoder bring-up test (ESP32-C3 SuperMini)
// Reads both wheel quadrature encoders and prints counts + revolutions.
// NO motor power needed — spin each wheel by hand to see the counts move.

const int L_A = 5;    // left  encoder A  (GPIO5)
const int L_B = 6;    // left  encoder B  (GPIO6)
const int R_A = 7;    // right encoder A  (GPIO7)
const int R_B = 10;   // right encoder B  (GPIO10)

const long COUNTS_PER_REV = 17280;  // 64 CPR x 270:1 gearing, 4x decode

volatile long   leftCount = 0,  rightCount = 0;
volatile uint8_t leftState = 0, rightState = 0;

// 4x quadrature transition table: index = (prevAB<<2 | nowAB)
const int8_t QEM[16] = {0,-1, 1, 0,  1, 0, 0,-1, -1, 0, 0, 1,  0, 1,-1, 0};

void IRAM_ATTR leftISR() {
  leftState = ((leftState << 2) | (digitalRead(L_A) << 1) | digitalRead(L_B)) & 0x0F;
  leftCount += QEM[leftState];
}
void IRAM_ATTR rightISR() {
  rightState = ((rightState << 2) | (digitalRead(R_A) << 1) | digitalRead(R_B)) & 0x0F;
  rightCount += QEM[rightState];
}

void setup() {
  Serial.begin(115200);
  delay(300);
  pinMode(L_A, INPUT); pinMode(L_B, INPUT);
  pinMode(R_A, INPUT); pinMode(R_B, INPUT);
  leftState  = (digitalRead(L_A) << 1) | digitalRead(L_B);
  rightState = (digitalRead(R_A) << 1) | digitalRead(R_B);
  attachInterrupt(digitalPinToInterrupt(L_A), leftISR,  CHANGE);
  attachInterrupt(digitalPinToInterrupt(L_B), leftISR,  CHANGE);
  attachInterrupt(digitalPinToInterrupt(R_A), rightISR, CHANGE);
  attachInterrupt(digitalPinToInterrupt(R_B), rightISR, CHANGE);
  Serial.println("\n=== SPARC encoder test ready — spin the wheels by hand ===");
}

void loop() {
  long l, r;
  noInterrupts(); l = leftCount; r = rightCount; interrupts();
  Serial.printf("LEFT %8ld cnt (%+.3f rev)    RIGHT %8ld cnt (%+.3f rev)\n",
                l, (double)l / COUNTS_PER_REV, r, (double)r / COUNTS_PER_REV);
  delay(250);
}

// SPARC rover — drive test (ESP32-C3 SuperMini)
// WHEELS RAISED for first run. Main switch is your cutoff. Boots with motors OFF.
//   f = forward     b = backward
//   l = pivot left  r = pivot right
//   s = stop        + / - = duty +/- 10%

// ---- direction calibration ----
const bool L_MOTOR_INVERT = true;   // left wheel ran backward -> flipped here
const bool R_MOTOR_INVERT = false;
const int  L_ENC_SIGN = 1;          // set -1 if LEFT rpm reads negative while moving forward
const int  R_ENC_SIGN = 1;          // set -1 if RIGHT rpm reads negative while moving forward

const int L_RPWM = 0,  L_LPWM = 1;
const int R_RPWM = 3,  R_LPWM = 4;
const int L_A = 5, L_B = 6;
const int R_A = 7, R_B = 10;

const long   COUNTS_PER_REV = 17280;
const double WHEEL_CIRC_M   = 0.2042;
const int    PWM_FREQ = 5000, PWM_RES = 8;

enum Mode { M_STOP, M_FWD, M_BACK, M_LEFT, M_RIGHT };
Mode mode = M_STOP;
int  dutyPct = 60;

volatile long    leftCount = 0,  rightCount = 0;
volatile uint8_t leftState = 0,  rightState = 0;
const int8_t QEM[16] = {0,-1, 1, 0,  1, 0, 0,-1, -1, 0, 0, 1,  0, 1,-1, 0};

unsigned long tPrev = 0;
long lPrev = 0, rPrev = 0;

void IRAM_ATTR leftISR()  { leftState  = ((leftState  << 2) | (digitalRead(L_A) << 1) | digitalRead(L_B)) & 0x0F; leftCount  += QEM[leftState];  }
void IRAM_ATTR rightISR() { rightState = ((rightState << 2) | (digitalRead(R_A) << 1) | digitalRead(R_B)) & 0x0F; rightCount += QEM[rightState]; }

// signed duty: + = forward, - = reverse
void setMotors(int l, int r) {
  if (L_MOTOR_INVERT) l = -l;
  if (R_MOTOR_INVERT) r = -r;
  if (l >= 0) { ledcWrite(L_LPWM, 0); ledcWrite(L_RPWM,  l); }
  else        { ledcWrite(L_RPWM, 0); ledcWrite(L_LPWM, -l); }
  if (r >= 0) { ledcWrite(R_LPWM, 0); ledcWrite(R_RPWM,  r); }
  else        { ledcWrite(R_RPWM, 0); ledcWrite(R_LPWM, -r); }
}

void resetBaseline() {
  noInterrupts(); lPrev = leftCount; rPrev = rightCount; interrupts();
  tPrev = millis();
}

const char* modeName() {
  switch (mode) { case M_FWD: return "FWD  "; case M_BACK: return "BACK "; case M_LEFT: return "LEFT "; case M_RIGHT: return "RIGHT"; default: return "STOP "; }
}

void applyMode() {
  int d = (dutyPct * 255) / 100;
  switch (mode) {
    case M_FWD:   setMotors( d,  d); break;
    case M_BACK:  setMotors(-d, -d); break;
    case M_LEFT:  setMotors(-d,  d); break;   // left back, right fwd -> pivot left
    case M_RIGHT: setMotors( d, -d); break;   // left fwd, right back -> pivot right
    default:      setMotors( 0,  0); break;
  }
  resetBaseline();
  Serial.printf("\n>>> %s @ %d%%\n", modeName(), dutyPct);
}

void setup() {
  Serial.begin(115200);
  delay(300);
  pinMode(L_A, INPUT); pinMode(L_B, INPUT); pinMode(R_A, INPUT); pinMode(R_B, INPUT);
  leftState  = (digitalRead(L_A) << 1) | digitalRead(L_B);
  rightState = (digitalRead(R_A) << 1) | digitalRead(R_B);
  attachInterrupt(digitalPinToInterrupt(L_A), leftISR,  CHANGE);
  attachInterrupt(digitalPinToInterrupt(L_B), leftISR,  CHANGE);
  attachInterrupt(digitalPinToInterrupt(R_A), rightISR, CHANGE);
  attachInterrupt(digitalPinToInterrupt(R_B), rightISR, CHANGE);

  ledcAttach(L_RPWM, PWM_FREQ, PWM_RES); ledcAttach(L_LPWM, PWM_FREQ, PWM_RES);
  ledcAttach(R_RPWM, PWM_FREQ, PWM_RES); ledcAttach(R_LPWM, PWM_FREQ, PWM_RES);
  setMotors(0, 0);
  resetBaseline();

  Serial.println("\n=== SPARC drive test — motors OFF ===");
  Serial.println("WHEELS RAISED.  f=fwd  b=back  l=pivot left  r=pivot right  s=stop  +/- = duty");
  Serial.printf("duty = %d%%\n", dutyPct);
}

void loop() {
  if (Serial.available()) {
    char c = Serial.read();
    switch (c) {
      case 'f': case 'F': mode = M_FWD;   applyMode(); break;
      case 'b': case 'B': mode = M_BACK;  applyMode(); break;
      case 'l': case 'L': mode = M_LEFT;  applyMode(); break;
      case 'r': case 'R': mode = M_RIGHT; applyMode(); break;
      case 's': case 'S': mode = M_STOP;  applyMode(); break;
      case '+': case '=': dutyPct = min(100, dutyPct + 10); applyMode(); break;
      case '-': case '_': dutyPct = max(0,   dutyPct - 10); applyMode(); break;
    }
  }

  unsigned long now = millis();
  if (now - tPrev >= 500) {
    noInterrupts(); long l = leftCount, r = rightCount; interrupts();
    double dt = (now - tPrev) / 1000.0;
    if (mode != M_STOP) {
      double lrev = L_ENC_SIGN * (double)(l - lPrev) / COUNTS_PER_REV;
      double rrev = R_ENC_SIGN * (double)(r - rPrev) / COUNTS_PER_REV;
      Serial.printf("%s %3d%%   LEFT %+7.2f rpm %+.4f m/s    RIGHT %+7.2f rpm %+.4f m/s\n",
                    modeName(), dutyPct, lrev / dt * 60.0, lrev * WHEEL_CIRC_M / dt,
                    rrev / dt * 60.0, rrev * WHEEL_CIRC_M / dt);
    }
    lPrev = l; rPrev = r; tPrev = now;
  }
  delay(5);
}

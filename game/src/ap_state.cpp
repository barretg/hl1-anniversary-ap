#include "ap_state.h"

namespace ap {

Snapshot& State() {
    static Snapshot state;
    return state;
}

}  // namespace ap

// Copyright 2024 The Pigweed Authors
//
// Licensed under the Apache License, Version 2.0 (the "License"); you may not
// use this file except in compliance with the License. You may obtain a copy of
// the License at
//
//     https://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
// WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
// License for the specific language governing permissions and limitations under
// the License.

#define ARRAY_LEN(array) (sizeof(array) / sizeof(*array))

// DOCSTAG: [static_assert-example]

#include "pw_polyfill/static_assert.h"

extern int array[3];

static_assert(ARRAY_LEN(array) == 3, "The array must contain 3 elements");

static_assert(sizeof(array) == 3 * sizeof(int));  // The message is optional.

// DOCSTAG: [static_assert-example]

#if 0  // failing asserts

static_assert(0);  // no message
static_assert(0, "This static assert should FAIL");

#endif  // 0

// static_assert should continue to work even if <assert.h> is included, but,
// depending on the library, the <assert.h> version of static_assert may
// override pw_polyfill's, so the message argument may be required.

#include <assert.h>

static_assert(1, "This static assert should PASS");
